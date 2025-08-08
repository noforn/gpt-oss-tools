# gpt-oss-tools

gpt-oss-tools is a command-line assistant that combines a language model with several helpful utilities.  It uses the `agents` framework to run an interactive chat session and exposes tools for web search, URL browsing, weather lookups, and executing Python code in a sandboxed environment.

## Key Features

- **Interactive agent chat** &ndash; Start a conversation with a local model and get markdown-formatted answers in the terminal.
- **Web search and page browsing** &ndash; Query DuckDuckGo and summarize the contents of specific web pages for up-to-date information.
- **Weather reports** &ndash; Automatically detect your location and fetch forecasts from weather.gov.
- **Restricted Python execution** &ndash; Run code safely in a persistent sandbox for calculations or quick experiments.
- **Smart home automation** &ndash; Control Kasa smart lights by turning them on/off, adjusting brightness, or reading their current state.
- **Web-based interface** &ndash; Launch a FastAPI-powered UI to chat with the assistant from your browser.

## Use Cases

- Research current events or gather information from the web.
- Generate quick scripts or perform calculations without leaving the chat.
- Check the weather for your current location or for specific coordinates.
- Explore or prototype tool-augmented agent behaviours.
- Manage smart home devices such as Kasa lights.
- Use a browser-based interface for a more visual chat experience.

## Getting Started

1. Create and activate a Python 3.13 virtual environment with **uv**:
   ```bash
   uv venv env --python 3.13
   source env/bin/activate
   ```
2. Install the required packages using uv's pip:
   ```bash
   uv pip install "openai-agents[litellm]" ddgs requests beautifulsoup4 \
       rich termcolor RestrictedPython pylatexenc fastapi uvicorn \
       python-kasa python-dotenv
   ```
3. Download the local model used by the assistant:
   ```bash
   ollama pull gpt-oss:20b
   ```
4. Choose an interface to start:
   - **Command line**
     ```bash
     python gpt-oss-tools.py
     ```
   - **Web UI**
     ```bash
     python -c "from web_ui import run_web_ui; run_web_ui('gpt-oss:20b', '<api-key>')"
     ```
5. Type your questions or commands. In the CLI, enter `bye` to exit the session.

## License

This project is licensed under the MIT License.  See the LICENSE file for details.

