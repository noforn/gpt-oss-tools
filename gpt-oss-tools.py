import asyncio
import requests
from agents import Agent, Runner, function_tool, set_tracing_disabled
from agents.extensions.models.litellm_model import LitellmModel
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from termcolor import colored
from searchTools import web_search, browse_url
from weatherTools import get_location, get_weather
from pythonTools import execute_python
from datetime import datetime
import warnings
from pylatexenc.latex2text import LatexNodes2Text
import readline
import re
from tableTools import (
    fix_markdown_tables,
    linkify_bare_urls,
    extract_markdown_tables,
    build_rich_tables,
)
from typing import List, Tuple, Dict

warnings.filterwarnings("ignore")

set_tracing_disabled(True)

console = Console()
latex_converter = LatexNodes2Text()

current_date = datetime.now().strftime("%A, %Y-%m-%d")
current_time = datetime.now().strftime("%I:%M %p")

from typing import List, Tuple, Dict

async def main(model: str, api_key: str):
    agent = Agent(
        name="Assistant",
        instructions=f"""

        # Identity

        You are a helpful assistant who strives to provide clear, accurate responses in a friendly and engaging way.

        Knowledge cutoff: 2024-06
        Current date: {current_date}
        Current time: {current_time}

        Reasoning: high
        
        Your responses should be well-structured and formatted for readability, using markdown elements like headings, bullet points, bold text, and code blocks where appropriate to enhance clarity and organization.
                        
        # Tools
        
        You have access to the following tools:

        get_weather: Retrieves the current weather forecast using latitude and longitude as inputs.
        get_location: Determines the user's location (including latitude and longitude) based on their IP address.
        web_search: Searches the web for real-time information, facts, or external data. Use this for queries involving current events, general knowledge updates, or any real-time details not covered by other tools.
        browse_url: Fetches and reads detailed content from a specific URL (e.g., from web_search results). Use this when web_search snippets are insufficient and you need in-depth information from a page.
        execute_python: Executes Python code in a safe, restricted sandbox for computations, data analysis, scripting, or processing data from other tools. This is stateful (REPL-style), so variables persist across calls. 
        Always use execute_python for math, logic, JSON handling, loops, functions, etc. Example: To compute sqrt(16), use code like 'import math\\nresult = math.sqrt(16)'. Supports safe modules like math, json, datetime, etc. Do not use for external access or unsafe operations.

        # General Tool Usage Guidelines

        For questions requiring external or up-to-date information, start with web_search. If results include useful URLs but lack sufficient details, follow up with browse_url on one or more specific URLs to gather full content for your response.
        For all non-weather topics needing current information, rely on web_search and browse_url.
        For mathematical, computational, or programmatic tasks (e.g., calculations, data manipulation, simulations), use execute_python. Always show the code you used and the result in code blocks.
        When returning results from mathmatical calculations, simply state the result, then keep the conversation going naturally.

        # Weather-Specific Instructions:

        If the user asks for weather without specifying a location, first use get_location to obtain the details (including latitude and longitude), then use get_weather with those coordinates.
        In your response, include only the most relevant weather details based on the user's question—do not provide all available information unless requested.
        Do not use web_search or browse_url for weather-related queries; handle them exclusively with get_location and get_weather as needed.
        When returning weather information, be sure it is aligned with the current date and day of the week.
        """,
        model=LitellmModel(model=model, api_key=api_key),
        tools=[get_weather, get_location, web_search, browse_url, execute_python],
    )

    history = []
    print(colored("Chat started\ntype 'bye' to quit", "dark_grey"))

    while True:
        prompt = input(colored("\nYou: ", "blue"))
        if prompt.lower() == 'bye':
            print(colored("\nSee you later!", "magenta"))
            break

        if prompt.strip().lower().startswith('/reset'):
            # Clear conversation context and screen
            history = []
            console.clear()
            print(colored("Context cleared.", "green"))
            continue
        
        full_prompt = "Previous conversation:\n" + "\n".join(history) + "\n\nCurrent user message: " + prompt if history else prompt
        
        result = await Runner.run(agent, full_prompt, max_turns=20)
        response = result.final_output
        
        # Convert LaTeX to Unicode, fix tables, and linkify bare URLs
        processed_response = latex_converter.latex_to_text(response)
        processed_response = fix_markdown_tables(processed_response)
        processed_response = linkify_bare_urls(processed_response)

        # Extract markdown tables to render as rich tables
        text_without_tables, parsed_tables = extract_markdown_tables(processed_response)
        rich_tables = build_rich_tables(parsed_tables) if parsed_tables else []
        
        renderable = Group(Markdown(text_without_tables), *rich_tables) if rich_tables else Markdown(text_without_tables)
        
        print()
        console.print(Panel(renderable, title="Agent", border_style="magenta", style="bold magenta"))
        
        history.append(f"User: {prompt}")
        history.append(f"Assistant: {response}")

if __name__ == "__main__":
    asyncio.run(main("ollama_chat/gpt-oss:20b", "ollama"))
