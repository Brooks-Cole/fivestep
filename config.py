"""
Configuration settings for the 5-step process coaching application.
"""
import os
from datetime import timedelta

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()  # Load environment variables from .env file
    print("Environment variables loaded from .env file")
except ImportError:
    print("dotenv package not available, using default environment variables")
except Exception as e:
    print(f"Error loading environment variables: {str(e)}")

# Environment variables with secure defaults
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    raise EnvironmentError(
        "SECRET_KEY environment variable is not set. "
        "Please set it in your .env file or environment variables."
    )

# API Configuration
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
if not ANTHROPIC_API_KEY:
    raise EnvironmentError(
        "ANTHROPIC_API_KEY environment variable is not set. "
        "Please set it in your .env file or environment variables."
    )

# Model Configuration
DEFAULT_MODEL = "claude-3-5-sonnet-20240620"
MAX_TOKENS = 4000
MAX_HISTORY_MESSAGES = 50  # Maximum number of messages to keep in history

# Session Configuration
SESSION_CONFIG = {
    'SECRET_KEY': SECRET_KEY,
    'SESSION_PERMANENT': True,
    'PERMANENT_SESSION_LIFETIME': timedelta(hours=1),
    'SESSION_COOKIE_SECURE': True,
    'SESSION_COOKIE_HTTPONLY': True,
    'SESSION_COOKIE_SAMESITE': 'Lax',
}

# Step Definitions
STEPS = [
    {"number": 1, "name": "Have Clear Goals", "description": "Define a specific, measurable goal"},
    {"number": 2, "name": "Identify Problems", "description": "Identify obstacles preventing goal achievement"},
    {"number": 3, "name": "Diagnose Root Causes", "description": "Find the underlying reasons for problems"},
    {"number": 4, "name": "Design a Plan", "description": "Create an actionable plan to address root causes"},
    {"number": 5, "name": "Push Through to Completion", "description": "Establish execution habits and accountability"}
]

# Step Completion Marker
STEP_COMPLETE_MARKER = "STEP_COMPLETE"

# API Request Retry Configuration
MAX_RETRIES = 2
RETRY_DELAY = 2  # seconds between retries