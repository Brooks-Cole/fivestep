from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
import anthropic
from steps.step1 import handle_step1
from steps.step2 import handle_step2
from steps.step3 import handle_step3
from steps.step4 import handle_step4
from steps.step5 import handle_step5
import re
import os
import json
import logging
from config import (SESSION_CONFIG, STEPS, ANTHROPIC_API_KEY, 
                   STEP_COMPLETE_MARKER)
from utils import truncate_history, extract_goal, remove_step_headers, with_retry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def configure_sessions(app):
    """
    Configure sessions for Vercel deployment - serverless environment requires simpler session handling
    """
    # Apply all session configuration from config file
    for key, value in SESSION_CONFIG.items():
        app.config[key] = value
    
    return app

app = Flask(__name__)
app = configure_sessions(app)  # Configure sessions
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable caching for static files
CORS(app)

try:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    logger.info("Successfully initialized Anthropic client")
except Exception as e:
    logger.error(f"Error initializing Anthropic client: {str(e)}")
    raise RuntimeError(f"Failed to initialize Anthropic client: {str(e)}")

# Map step numbers to their functions
step_functions = {
    1: handle_step1,
    2: handle_step2,
    3: handle_step3,
    4: handle_step4,
    5: handle_step5
}

# Use steps from config
steps = STEPS

# New: Function to analyze rationality vs emotionality using Claude
def analyze_response_sentiment(user_input, client):
    """
    Analyzes whether a user response is more rational or emotional
    Returns a score from -10 (highly emotional) to +10 (highly rational)
    """
    system_content = """
    Analyze the following text and rate it on a rationality vs emotionality scale from -10 to +10:
    - -10 to -7: Highly emotional (dominated by feelings, passions, subjective experiences)
    - -6 to -3: Moderately emotional (contains emotional language but with some reasoning)
    - -2 to +2: Balanced (contains both emotional and rational elements in equilibrium)
    - +3 to +6: Moderately rational (logical with some emotional components)
    - +7 to +10: Highly rational (dominated by logic, evidence, structured reasoning)
    
    Provide ONLY a single number score between -10 and +10 without any explanation.
    """
    
    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=10,
            system=system_content,
            messages=[{"role": "user", "content": user_input}]
        )
        score_text = response.content[0].text.strip()
        
        # Extract numeric score, handling potential formatting issues
        score = None
        try:
            # Try direct conversion first
            score = int(score_text)
        except ValueError:
            # If that fails, search for a number pattern
            import re
            number_pattern = r'-?\d+'
            match = re.search(number_pattern, score_text)
            if match:
                score = int(match.group(0))
        
        # Ensure score is within bounds
        if score is not None:
            return max(min(score, 10), -10)
        else:
            return 0  # Default to neutral if parsing fails
    except Exception as e:
        logger.error(f"Error analyzing sentiment: {str(e)}")
        return 0  # Default to neutral on error

def generate_email_summary(session_data):
    """
    Generates an email summary of the 5-step process results
    that can be shared with colleagues or management.
    
    Args:
        session_data: Dictionary containing the session data including
                     goal, completed steps, and evaluation summaries
    
    Returns:
        str: Formatted email content
    """
    goal = session_data.get('goal', 'Not specified')
    
    # Get evaluation summaries from each step
    step_evaluations = session_data.get('step_evaluations', {})
    
    # Format the email
    email_content = f"""
Subject: Process Improvement Analysis: {goal}

Dear Team,

I recently conducted a structured analysis of our current process related to: "{goal}". 
I'd like to share the findings to help us identify common pain points and collaborate on improvements.

## Goal
{goal}

## Key Problems Identified
{step_evaluations.get('2', 'No problems identified yet.')}

## Root Causes
{step_evaluations.get('3', 'Root causes not analyzed yet.')}

## Proposed Plan
{step_evaluations.get('4', 'Plan not developed yet.')}

## Implementation Strategy
{step_evaluations.get('5', 'Implementation strategy not developed yet.')}

I believe addressing these issues could significantly improve our workflow efficiency and reduce frustration. 
I'd appreciate your input on these findings and any additional pain points you've experienced that might not be captured here.

Could you please review and let me know:
1. Do these findings align with your experience?
2. Are there additional issues you've encountered?
3. Do you have any suggestions for the proposed solutions?

Thank you for your time and collaboration.

Regards,
[Your Name]
"""
    return email_content

class SessionState:
    """Class to manage session state more robustly instead of using magic strings"""
    
    def __init__(self, session_obj):
        self.session = session_obj
        self._initialize_if_needed()
    
    def _initialize_if_needed(self):
        """Initialize session if needed"""
        if 'current_step' not in self.session:
            logger.info("Initializing new session")
            self.session['current_step'] = 1
            self.session['completed_steps'] = []
            self.session['history'] = []
            self.session['goal'] = None
            self.session['step_evaluations'] = {}
            # New: Initialize sentiment EMA with 0 (neutral)
            self.session['sentiment_ema'] = 0
    
    @property
    def current_step(self):
        return self.session.get('current_step', 1)
    
    @current_step.setter
    def current_step(self, value):
        self.session['current_step'] = value
    
    @property
    def completed_steps(self):
        return self.session.get('completed_steps', [])
    
    def add_completed_step(self, step):
        if step not in self.completed_steps:
            completed = self.completed_steps.copy()
            completed.append(step)
            self.session['completed_steps'] = completed
    
    @property
    def history(self):
        return self.session.get('history', [])
    
    @history.setter
    def history(self, value):
        # Apply compression before storing to reduce cookie size
        self.session['history'] = truncate_history(value)
    
    def add_message(self, role, content):
        history = self.history.copy()
        history.append({'role': role, 'content': content})
        
        # Ensure we never exceed our cookie size limit by aggressive truncation if needed
        if len(str(history)) > 3500:  # Leave some margin for other session data
            logger.warning("History size exceeding safe limit, performing aggressive truncation")
            # Keep only last 5 messages to prevent cookie overflow
            history = history[-5:]
            
        self.history = history
    
    @property
    def goal(self):
        return self.session.get('goal')
    
    @goal.setter
    def goal(self, value):
        self.session['goal'] = value
    
    @property
    def step_evaluations(self):
        return self.session.get('step_evaluations', {})
    
    def add_evaluation(self, step, evaluation):
        evaluations = self.step_evaluations.copy()
        evaluations[str(step)] = evaluation
        self.session['step_evaluations'] = evaluations
    
    # New: Properties for sentiment tracking
    @property
    def sentiment_ema(self):
        return self.session.get('sentiment_ema', 0)
    
    @sentiment_ema.setter
    def sentiment_ema(self, value):
        self.session['sentiment_ema'] = value
    
    def reset(self):
        """Reset session state"""
        self.session.clear()
        if self.session.get('_flashes'):
            del self.session['_flashes']
        self._initialize_if_needed()


@app.route('/chat', methods=['POST'])
def chat():
    try:
        # Use our new SessionState class to manage state
        state = SessionState(session)
        
        data = request.get_json()
        user_input = data.get('user_input', '')
        
        # New: Calculate sentiment score using Claude and update EMA
        sentiment_score = analyze_response_sentiment(user_input, client)
        alpha = 0.3  # Smoothing factor for EMA
        new_ema = alpha * sentiment_score + (1 - alpha) * state.sentiment_ema
        state.sentiment_ema = new_ema
        
        # Get and truncate history to manage token count
        history = truncate_history(state.history)
        goal = state.goal
        current_step = state.current_step
        step_function = step_functions[current_step]
        
        # Handle special case for first message - we'll auto-generate a welcome message
        if len(history) == 0 and user_input.lower() in ['hi', 'hello', 'hey', 'start']:
            welcome_message = (
                "STEP 1: HAVE CLEAR GOALS\n\n"
                " Hi there! What goal would you like to focus on today? "
                "Think about something meaningful you're working toward. The more specific you can be, the better we can work together.\n\n"
                "CURRENT STEP: 1 - HAVE CLEAR GOALS"
            )
            
            # Update conversation history with full message including markers (for system use)
            state.add_message('user', user_input)
            state.add_message('assistant', welcome_message)
            
            # Clean welcome message for user display
            cleaned_welcome = remove_step_headers(welcome_message)
            
            return jsonify({
                'main_response': cleaned_welcome,
                'evaluation_summary': '',
                'completed_steps': [],
                'current_step': 1,
                'step_info': get_step_info(1),
                # Include sentiment data for UI theming only
                'sentiment_score': sentiment_score,
                'sentiment_ema': state.sentiment_ema,
                # Bot name will be generated in the frontend
            })
        
        # Normal flow for all other messages - with retry
        # Do NOT modify the step function calls or pass sentiment info to them
        main_response, is_complete, evaluation_summary = step_function(user_input, history, goal, client)

        # Update conversation history
        state.add_message('user', user_input)
        state.add_message('assistant', main_response)

        # Store evaluation summary for this step if provided
        if evaluation_summary:
            state.add_evaluation(current_step, evaluation_summary)

        # Handle step completion
        if is_complete:
            state.add_completed_step(current_step)
            
            if current_step == 1:
                # Extract and store goal from step 1 completion
                extracted_goal = extract_goal(main_response)
                if extracted_goal:
                    state.goal = extracted_goal
                else:
                    logger.warning("Could not extract goal from step 1 completion")
            
            # Move to next step if not on final step
            if current_step < 5:
                state.current_step = current_step + 1

        # Prepare data for frontend
        completed_steps = [
            {
                'step': i, 
                'name': next((s['name'] for s in steps if s['number'] == i), f"Step {i}"),
                'description': next((s['description'] for s in steps if s['number'] == i), ""),
                'goal': state.goal if i == 1 else None,
                'is_step_one': i == 1
            }
            for i in state.completed_steps
        ]
        
        # Clean response for user display
        cleaned_response = remove_step_headers(main_response)

        return jsonify({
            'main_response': cleaned_response,
            'evaluation_summary': evaluation_summary,
            'completed_steps': completed_steps,
            'current_step': state.current_step,
            'step_info': get_step_info(state.current_step),
            # Include sentiment data for UI theming only
            'sentiment_score': sentiment_score,
            'sentiment_ema': state.sentiment_ema,
            # Bot name will be generated in the frontend
        })
    except anthropic.APIError as api_err:
        # Handle API-specific errors
        logger.error(f"Anthropic API error: {str(api_err)}")
        error_type = type(api_err).__name__
        
        if isinstance(api_err, anthropic.RateLimitError):
            user_message = "The AI service is currently overloaded. Please try again in a moment."
        elif isinstance(api_err, anthropic.APITimeoutError):
            user_message = "The request timed out. Please try again or reset the conversation."
        elif isinstance(api_err, anthropic.APIConnectionError):
            user_message = "Could not connect to the AI service. Please check your internet connection."
        else:
            user_message = "There was an issue with the AI service. Please try again later."
            
        # Get sentiment EMA for bot name
        sentiment_ema = session.get('sentiment_ema', 0)
        
        return jsonify({
            'main_response': user_message,
            'evaluation_summary': f"API Error ({error_type}): {str(api_err)}",
            'completed_steps': session.get('completed_steps', []),
            'current_step': session.get('current_step', 1),
            'step_info': get_step_info(session.get('current_step', 1)),
            'sentiment_score': 0,
            'sentiment_ema': sentiment_ema
            # Bot name will be generated in the frontend
        }), 500
        
    except Exception as e:
        # Handle any other errors
        error_message = f"An error occurred: {str(e)}"
        logger.error(error_message, exc_info=True)
        
        # Create a more user-friendly message
        user_error_message = "I encountered an error. Please try again or reset the conversation."
        
        # Check for common error patterns
        error_str = str(e).lower()
        if "token" in error_str or "exceed" in error_str or "overload" in error_str:
            user_error_message = "The conversation has become too long. Please reset the conversation to continue."
        
        # Get sentiment EMA for bot name
        sentiment_ema = session.get('sentiment_ema', 0)
        
        return jsonify({
            'main_response': user_error_message,
            'evaluation_summary': error_message,
            'completed_steps': session.get('completed_steps', []),
            'current_step': session.get('current_step', 1),
            'step_info': get_step_info(session.get('current_step', 1)),
            'sentiment_score': 0,
            'sentiment_ema': sentiment_ema
            # Bot name will be generated in the frontend
        }), 500

def get_step_info(step_number):
    """Returns information about the current step"""
    step_info = next((s for s in steps if s['number'] == step_number), None)
    if not step_info:
        return {"number": step_number, "name": f"Step {step_number}", "description": ""}
    return step_info

@app.route('/set_step', methods=['POST'])
def set_step():
    state = SessionState(session)
    data = request.get_json()
    step = data['step']
    
    # Ensure they can only go to a completed step or the current step
    if step in state.completed_steps or step == state.current_step:
        state.current_step = step
        return jsonify({
            'status': 'success',
            'current_step': step,
            'step_info': get_step_info(step),
            'sentiment_ema': state.sentiment_ema
        })
    return jsonify({'status': 'error', 'message': 'Step not completed yet'}), 403

@app.route('/reset', methods=['POST'])
def reset_conversation():
    # Use SessionState to reset all session data
    state = SessionState(session)
    state.reset()
    
    return jsonify({
        'status': 'success',
        'current_step': 1,
        'step_info': get_step_info(1),
        'sentiment_ema': 0
    })

@app.route('/get_summary', methods=['GET'])
def get_summary():
    """Endpoint to generate and return an email summary of the process"""
    state = SessionState(session)
    
    # Create summary data
    summary_data = {
        'goal': state.goal if state.goal else 'Not specified',
        'step_evaluations': state.step_evaluations
    }
    
    # Generate the email content
    email_content = generate_email_summary(summary_data)
    
    return jsonify({
        'email_content': email_content,
        'sentiment_ema': state.sentiment_ema
    })

@app.route('/progress', methods=['GET'])
def get_progress():
    """Returns the current progress through the 5-step process"""
    state = SessionState(session)
    
    return jsonify({
        'current_step': state.current_step,
        'completed_steps': state.completed_steps,
        'goal': state.goal,
        'step_info': get_step_info(state.current_step),
        'all_steps': steps,
        'sentiment_ema': state.sentiment_ema
    })

@app.route('/')
def serve_frontend():
    try:
        return send_from_directory('static', 'index.html')
    except Exception as e:
        print(f"Error serving index.html: {str(e)}")
        # Return a basic HTML response in case the static file can't be found
        return '<html><body><h1>5-Step Process</h1><p>There was an error loading the application. Please check the server logs.</p></body></html>'
    
@app.route('/api/health')
def health_check():
    """Enhanced health check endpoint to verify API and system status"""
    import sys
    import platform
    import time
    
    start_time = time.time()
    
    # Check if we can connect to Anthropic API
    api_status = {
        "status": "ok",
        "message": "Connection successful"
    }
    
    try:
        # Do a simple API check with retry logic
        @with_retry(max_retries=1, delay=1)
        def test_api_connection():
            return client.models.list()
            
        _ = test_api_connection()
    except Exception as e:
        error_type = type(e).__name__
        api_status = {
            "status": "error",
            "message": str(e),
            "error_type": error_type
        }
        logger.warning(f"API health check failed: {error_type} - {str(e)}")
    
    # Check environment variables are properly set
    env_status = {
        "api_key_set": bool(ANTHROPIC_API_KEY),
        "secret_key_set": bool(SESSION_CONFIG.get('SECRET_KEY')),
    }
    
    # Check session config
    session_config_summary = {k: "***" if k == "SECRET_KEY" else "set" 
                            for k, v in SESSION_CONFIG.items() if v}
    
    response_time = time.time() - start_time
    
    return jsonify({
        "status": "ok" if api_status["status"] == "ok" else "degraded",
        "version": "1.1",
        "environment": os.environ.get('VERCEL_ENV', 'development'),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "response_time_ms": round(response_time * 1000, 2),
        "api": api_status,
        "environment_variables": env_status,
        "session_config": session_config_summary,
        "sentiment_analysis": "enabled"
    })

# The following makes the app work both locally and on Vercel
if __name__ == '__main__':
    app.run(debug=True, port=5000)
    
# This is needed for Vercel deployment
# Do not remove - Vercel uses this to import your Flask app
# Exporting the application for WSGI servers
application = app