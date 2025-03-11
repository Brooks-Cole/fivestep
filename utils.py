"""
Utility functions for the 5-step process coaching application.
"""
import re
import time
import functools
from typing import List, Dict, Tuple, Optional, Any, Callable
import anthropic
from config import MAX_RETRIES, RETRY_DELAY, MAX_HISTORY_MESSAGES, STEP_COMPLETE_MARKER

def truncate_history(history: List[Dict[str, str]], max_messages: int = MAX_HISTORY_MESSAGES) -> List[Dict[str, str]]:
    """
    Truncate conversation history if needed to prevent token limit issues.
    Also compresses content to reduce cookie size.
    
    Args:
        history: List of message dictionaries
        max_messages: Maximum number of messages to keep
        
    Returns:
        Truncated history list
    """
    if not history:
        return []
        
    # First truncate the list if it's too long
    if len(history) > max_messages:
        # Keep the most recent messages
        history = history[-max_messages:]
    
    # Then compress the content of older messages to reduce cookie size
    # Keep the last 10 messages intact, compress older ones
    if len(history) > 10:
        for i in range(len(history) - 10):
            # Compress user messages more aggressively than assistant responses
            if history[i]['role'] == 'user':
                # Keep only first 100 chars of user messages
                if len(history[i]['content']) > 100:
                    history[i]['content'] = history[i]['content'][:100] + "..."
            else:
                # For assistant messages, keep about half of the content
                content_len = len(history[i]['content'])
                if content_len > 200:
                    # Keep first paragraph, middle ellipsis, last paragraph
                    first_part = history[i]['content'][:100]
                    last_part = history[i]['content'][-100:]
                    history[i]['content'] = f"{first_part}...[content trimmed]...{last_part}"
    
    return history

def extract_goal(response: str) -> Optional[str]:
    """
    Extract the confirmed goal from the response text.
    More robust implementation with multiple patterns.
    
    Args:
        response: Response text containing the goal
        
    Returns:
        Extracted goal or None if not found
    """
    # Try several patterns to extract the goal
    patterns = [
        r'Goal confirmed: (.+?)(?:\.|\!)',
        r'goal is: (.+?)(?:\.|\!)',
        r'focusing on (.+?)(?:\.|\!)',
        r'aiming to (.+?)(?:\.|\!)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, response)
        if match:
            goal = match.group(1).strip()
            # Further clean the goal by removing any text after certain phrases
            for cutoff in ["I'll help", "Let's begin", "Let's move", "Now let's", "Your insight"]:
                if cutoff in goal:
                    goal = goal.split(cutoff)[0].strip()
            return goal
    
    # Fallback method if patterns don't match
    if "Goal confirmed" in response:
        parts = response.split("Goal confirmed:")
        if len(parts) > 1:
            goal_part = parts[1].strip()
            # Extract until the end of sentence or first period
            end_index = goal_part.find('.')
            if end_index != -1:
                goal = goal_part[:end_index].strip()
            else:
                # If no period, try finding "Moving to next step"
                end_index = goal_part.find('Moving to next step')
                if end_index != -1:
                    goal = goal_part[:end_index].strip()
                else:
                    goal = goal_part.strip()
                    
            # Further clean the goal by removing any text after certain phrases
            for cutoff in ["I'll help", "Let's begin", "Let's move", "Now let's", "Your insight"]:
                if cutoff in goal:
                    goal = goal.split(cutoff)[0].strip()
            return goal
    
    return None

def remove_step_headers(response: str) -> str:
    """
    Remove STEP headers and footers from the response.
    
    Args:
        response: Response text with headers/footers
        
    Returns:
        Cleaned response without headers/footers
    """
    # Remove the header (STEP X: TITLE)
    header_pattern = r'^STEP \d+: [A-Z\s]+'
    response = re.sub(header_pattern, '', response)
    
    # Remove the footer (CURRENT STEP: X - TITLE)
    footer_pattern = r'CURRENT STEP: \d+ - [A-Z\s]+$'
    response = re.sub(footer_pattern, '', response)
    
    # Remove the STEP_COMPLETE marker
    response = response.replace(STEP_COMPLETE_MARKER, "")
    
    # Clean up any extra whitespace created by removing markers
    response = re.sub(r'\n\s*\n\s*\n', '\n\n', response).strip()
    
    return response

def extract_evaluation(response: str) -> Tuple[str, str]:
    """
    Extract evaluation sections from response and clean the main response.
    
    Args:
        response: Response text containing evaluation tags
        
    Returns:
        Tuple of (cleaned_response, evaluation_summary)
    """
    evaluation_summary = ""
    if "<evaluation>" in response and "</evaluation>" in response:
        evaluation_start = response.find("<evaluation>") + len("<evaluation>")
        evaluation_end = response.find("</evaluation>")
        evaluation_summary = response[evaluation_start:evaluation_end].strip()

        # Remove the evaluation tags and content from the main response
        response = response[:response.find("<evaluation>")] + response[response.find("</evaluation>") + len("</evaluation>"):]
    
    return response, evaluation_summary

def check_step_completion(response: str) -> bool:
    """
    Check if the step is complete based on response markers.
    
    Args:
        response: Response text to check
        
    Returns:
        True if the step is complete, False otherwise
    """
    completion_markers = [
        STEP_COMPLETE_MARKER,
        "Goal confirmed", 
        "goal is confirmed", 
        "confirmed your goal"
    ]
    
    return any(marker in response for marker in completion_markers)

def with_retry(max_retries: int = MAX_RETRIES, delay: int = RETRY_DELAY) -> Callable:
    """
    Decorator to add retry logic to API calls.
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Delay between retries in seconds
        
    Returns:
        Decorated function with retry logic
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (anthropic.RateLimitError, 
                       anthropic.APITimeoutError, 
                       anthropic.BadRequestError,
                       anthropic.APIConnectionError) as e:
                    last_exception = e
                    if attempt < max_retries:
                        # Exponential backoff with jitter
                        sleep_time = delay * (2 ** attempt) + (time.time() % 1)
                        time.sleep(sleep_time)
                    else:
                        break
            # If we've exhausted our retries, raise the last exception
            raise last_exception
        return wrapper
    return decorator