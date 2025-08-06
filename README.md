# gpt-oss-tools

gpt-oss-tools is a command-line assistant that combines a language model with several helpful utilities.  It uses the `agents` framework to run an interactive chat session and exposes tools for web search, URL browsing, weather lookups, and executing Python code in a sandboxed environment.

## Key Features

- **Interactive agent chat** &ndash; Start a conversation with a local model and get markdown-formatted answers in the terminal.
- **Web search and page browsing** &ndash; Query DuckDuckGo and summarize the contents of specific web pages for up-to-date information.
- **Weather reports** &ndash; Automatically detect your location and fetch forecasts from weather.gov.
- **Restricted Python execution** &ndash; Run code safely in a persistent sandbox for calculations or quick experiments.

## Use Cases

- Research current events or gather information from the web.
- Generate quick scripts or perform calculations without leaving the chat.
- Check the weather for your current location or for specific coordinates.
- Explore or prototype tool-augmented agent behaviours.

## Getting Started

1. Create and activate a Python 3.13 virtual environment with **uv**:
   ```bash
   uv venv env --python 3.13
   source env/bin/activate
   ```
2. Install the required packages using uv's pip:
   ```bash
   uv pip install "openai-agents[litellm]" ddgs requests beautifulsoup4 \
       rich termcolor RestrictedPython pylatexenc
   ```
3. Download the local model used by the assistant:
   ```bash
   ollama pull gpt-oss:20b
   ```
4. Run the chat interface:
   ```bash
   python gpt-oss-tools.py
   ```
5. Type your questions or commands. Enter `bye` to exit the session.

## License

This project is licensed under the MIT License.  See the LICENSE file for details.

