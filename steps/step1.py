"""
Step 1: Have Clear Goals - Fast Version
"""
from .Program_Wide_Prompt import PROGRAM_WIDE_PROMPT
import sys
import os

# Add the parent directory to sys.path to import from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import truncate_history, extract_evaluation, check_step_completion, with_retry
from config import DEFAULT_MODEL, MAX_TOKENS

@with_retry()
def handle_step1(user_input, history, goal, client):
    """
    Guides the user through Step 1: Have Clear Goals with faster progression
    """
    # System content with minimal coaching instructions
    system_content = f"""{PROGRAM_WIDE_PROMPT}

You are guiding the user through Step 1: Have Clear Goals.
The user's current goal is: {goal if goal else "Not yet defined"}

## Fast Goal Identification Guidelines

1. If the user mentions a specific goal that's reasonably clear, confirm it and move to the next step.
   - As soon as you see a goal that's specific enough to work with, consider it valid
   - Don't insist on perfection - a workable goal is sufficient
   - Example valid goals: "finish the project by Friday", "improve team communication", "reduce errors by 10%"

2. If the user's input is too vague to be a goal and instead seems like a desire (e.g., "I want to be better"), ask clarifying questions:
   - "Could you make that more specific? For example, what do you want to be better at?"
   - Once they respond with ANY clarification, accept it as their goal

3. If the user provides multiple goals, simply ask them to choose one:
   - "You've mentioned several goals. We want to avoid the pitfall of pursuing too many goals at once and achieving few or none of them. Which one would you like to focus on first?"
   - Accept whatever they choose immediately

4. As soon as you've identified a workable goal:
   - Include "STEP_COMPLETE" in your response (invisible to user)
   - Confirm with: "Goal confirmed: [user's goal]"
   - Immediately transition with: "Now, let's identify what obstacles might be in your way."

<evaluation>Keep this extremely brief - one sentence maximum.</evaluation>

The MOMENT you identify a specific, workable goal, confirm it and move on. Don't wait for multiple exchanges.
"""

    # Prepare the message history for Claude
    messages = truncate_history(history) if history else []
    
    # Add current user input
    messages.append({"role": "user", "content": user_input})
        
    # Make API call with retry logic handled by decorator
    api_response = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=MAX_TOKENS,
        system=system_content,
        messages=messages
    )
    
    response = api_response.content[0].text

    # Extract evaluation summary and clean response
    response, evaluation_summary = extract_evaluation(response)
    
    # Check for step completion markers
    is_complete = check_step_completion(response)
                   
    return response, is_complete, evaluation_summary