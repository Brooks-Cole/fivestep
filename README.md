# FiveStep Process Coach

A web application that guides users through Ray Dalio's 5-step process for achieving goals:

1. Have Clear Goals
2. Identify Problems
3. Diagnose Root Causes
4. Design a Plan
5. Push Through to Completion

## Features

- Interactive conversation with an AI coach powered by Claude
- Step-by-step guidance through the 5-step process
- Progress tracking and evaluation summaries for each step
- Email summary generation for sharing results
- Mobile-friendly responsive design

## Setup and Installation

### Prerequisites

- Python 3.8 or higher
- An Anthropic API key

### Installation

1. Clone the repository
2. Create a virtual environment:
   ```
   python -m venv myenv
   source myenv/bin/activate  # On Windows: myenv\Scripts\activate
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Create a `.env` file with your keys:
   ```
   SECRET_KEY=your_random_secure_key_here
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   ```

### Running Locally

```
python app.py
```

Then open http://localhost:5000 in your browser.

## Project Structure

- `app.py` - Main Flask application with routes and session handling
- `config.py` - Centralized configuration settings
- `utils.py` - Shared utility functions
- `steps/` - Contains step-specific logic for each of the 5 steps
  - `Program_Wide_Prompt.py` - Shared prompt used across all steps
  - `step1.py` through `step5.py` - Step-specific implementations
- `static/` - Frontend assets
  - `index.html` - Main frontend interface

## Security Features

- Environment variable-based configuration
- Proper error handling for missing API keys
- Secure session management
- XSS protection with input sanitization

## Deployment

The application is configured for serverless environments using Vercel.

## License

[MIT License](LICENSE)