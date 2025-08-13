import asyncio
import requests
import os
import argparse
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
from lightTools import *
from calendarTools import list_calendar_events, create_calendar_event, delete_calendar_event
from taskTools import schedule_task, check_tasks, delete_task
from taskScheduler import TaskScheduler
from stockTools import get_stock_price

warnings.filterwarnings("ignore")

set_tracing_disabled(True)

console = Console()
latex_converter = LatexNodes2Text()

current_date = datetime.now().strftime("%A, %Y-%m-%d")
current_time = datetime.now().strftime("%I:%M %p")
weekday = datetime.now().strftime("%A")
date_month= datetime.now().strftime("%B %-d, %Y")


def _is_ollama_tool_template_error(exc: Exception) -> bool:
    text = str(exc)
    return (
        "template:" in text and "slice index out of range" in text
    ) or (
        "/api/chat" in text and "500" in text and "Ollama" in text
    )

async def main(model: str, api_key: str):
    if os.getenv("LITELLM_DEBUG", "0") in ("1", "true", "True"):
        try:
            import litellm
            litellm._turn_on_debug()
        except Exception:
            pass

    instructions_text = f"""

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
        browse_url: Fetches and reads detailed content from a specific URL (e.g., from web_search results). It first tries a fast static fetch; if the page is JS-heavy or blocked, enable JS rendering with 'use_js=True' (requires Playwright). Supports optional 'proxy' and 'timeout_seconds'.
        turn_on_light: Turns on the lights.
        turn_off_light: Turns off the lights.
        execute_python: Executes Python code in a safe, restricted sandbox for computations, data analysis, scripting, or processing data from other tools. This is stateful (REPL-style), so variables persist across calls. 
        Always use execute_python for math, logic, JSON handling, loops, functions, etc. Example: To compute sqrt(16), use code like 'import math\\nresult = math.sqrt(16)'. Supports safe modules like math, json, datetime, etc. Do not use for external access or unsafe operations.
        list_calendar_events: Lists all calendar events.
        create_calendar_event: Creates a new calendar event.
        delete_calendar_event: Deletes a calendar event.
        schedule_task: Schedule a future or recurring task (store session_id, task_id, prompt, and VEVENT).
        check_tasks: List scheduled tasks and their status (upcoming/completed).
        delete_task: Delete a scheduled task by task id.
        get_stock_price: Get the latest stock price for the given ticker symbol.

        # General Tool Usage Guidelines

        For questions requiring external or up-to-date information, start with web_search. If results include useful URLs but lack sufficient details, follow up with browse_url on one or more specific URLs to gather full content for your response.
        For all non-weather topics needing current information, rely on web_search and browse_url.
        For mathematical, computational, or programmatic tasks (e.g., calculations, data manipulation, simulations), use execute_python. Always show the code you used and the result in code blocks.
        When returning results from mathmatical calculations, simply state the result, then keep the conversation going naturally.
        
        # Calendar-Specific Instructions:

        If the user asks about upcoming events, meetings, or schedules, use list_calendar_events.
        If the user asks you to add or schedule a new event, use create_calendar_event.
        If the user asks to remove or cancel an event, use delete_calendar_event.
        When creating an event, only confirm the details with the user before finalizing if they are not given. If you have what you need, create the event without asking for confirmation. Always use EST for time zone.
        When listing events, default to showing the next 5 upcoming events unless the user specifies otherwise.
        If the user does not provide a date/time for listing or creating events, ask them for it.
        Use natural, concise language to summarize events rather than tables, unless the user explicitly requests a table format.
        If a query is ambiguous (e.g., "Book lunch with Sarah"), clarify details before creating the event.
        Always respond in 12hr time format.
        # IMPORTANT:
        In your response, always make sure days of the week are accurate, today is {weekday}, and the date is {date_month}.


        # Light-Specific Instructions:

        If the user asks you to turn on the lights, use the turn_on_light tool.
        If the user asks you to turn off the lights, use the turn_off_light tool.
        If the user asks you to set the brightness of the lights, use the set_light_brightness tool.
        If the user asks you to set the color of the lights, use the set_light_hsv tool. Use get_light_state to check the current brightness and keep it the same when setting the color.
        If the user asks you to get the state of the lights, use the get_light_state tool.
        If it would be useful to check the state of the lights before using any of the other light tools, use the get_light_state tool.
        Avoid using tables or bullets when describing the state of the lights, use natural language instead.

        # Weather-Specific Instructions:

        If the user asks for weather without specifying a location, first use get_location to obtain the details (including latitude and longitude), then use get_weather with those coordinates.
        In your response, include only the most relevant weather details based on the user's question—do not provide all available information unless requested.
        Do not use web_search or browse_url for weather-related queries; handle them exclusively with get_location and get_weather as needed.
        When returning weather information, be sure it is aligned with the current date and day of the week.

        # Task-Specific Instructions:

        The current time is {formatted_time}.

        Use schedule_task to schedule future or recurring actions for yourself. Provide a clear VEVENT with a DTSTART (and optional RRULE). Example VEVENT:
        BEGIN:VEVENT
        DTSTART;TZID=America/New_York:20250101T090000
        RRULE:FREQ=DAILY;INTERVAL=1
        END:VEVENT

        Use check_tasks to review your upcoming or completed tasks. Use delete_task to remove tasks by their id.
        You don't need to tell the user what the task ID is. Don't use emojis.
        # IMPORTANT:
        Always verify the DTSTART is relative to the current time.
        When saving the prompt, make sure to use natural language and formulate the prompt as if you are the user.
        BAD EXAMPLE: "get_stock_price ticker=NVDA; get_stock_price ticker=TSM; get_stock_price ticker=AAPL"
        GOOD EXAMPLE: "Check the stock price for AAPL, NVDA, and TSM"
        NEVER USE NEW LINES IN TASK PROMPTS!
        """

    agent = Agent(
        name="Assistant",
        instructions=instructions_text,
        model=LitellmModel(model=model, api_key=api_key),
        tools=[get_weather, get_location, web_search, browse_url, execute_python, 
        turn_on_light, turn_off_light, set_light_brightness, set_light_hsv, get_light_state, 
        list_calendar_events, create_calendar_event, delete_calendar_event,
        schedule_task, check_tasks, delete_task, get_stock_price],
    )

    history = []
    print(colored("Chat started\ntype 'bye' to quit", "dark_grey"))

    # Start a background scheduler in CLI mode that injects into this same session/history
    scheduler = TaskScheduler()

    async def _inject_cli_message(session_id: str, message: str):
        nonlocal history
        full_prompt = "Previous conversation:\n" + "\n".join(history) + "\n\nCurrent user message: " + message if history else message
        result = await Runner.run(agent, full_prompt, max_turns=20)
        response = result.final_output

        processed_response = latex_converter.latex_to_text(response)
        processed_response = fix_markdown_tables(processed_response)
        processed_response = linkify_bare_urls(processed_response)
        text_without_tables, parsed_tables = extract_markdown_tables(processed_response)
        rich_tables = build_rich_tables(parsed_tables) if parsed_tables else []
        renderable = Group(Markdown(text_without_tables), *rich_tables) if rich_tables else Markdown(text_without_tables)

        print()
        console.print(Panel(renderable, title="Agent (scheduled task)", border_style="magenta", style="bold magenta"))

        history.append(f"User: {message}")
        history.append(f"Assistant: {response}")

    await scheduler.start(_inject_cli_message)

    while True:
        prompt = input(colored("\nYou: ", "blue"))
        if prompt.lower() == 'bye':
            print(colored("\nSee you later!", "magenta"))
            break

        if prompt.strip().lower().startswith('/reset'):
            history = []
            console.clear()
            print(colored("Context cleared.", "blue"))
            continue
        
        full_prompt = "Previous conversation:\n" + "\n".join(history) + "\n\nCurrent user message: " + prompt if history else prompt
        
        try:
            result = await Runner.run(agent, full_prompt, max_turns=20)
        except Exception as e:
            if _is_ollama_tool_template_error(e):
                console.print("\nHmm, something went wrong. Retrying without tools...", style="yellow")
                fallback_agent = Agent(
                    name="Assistant",
                    instructions=instructions_text,
                    model=LitellmModel(model=model, api_key=api_key),
                    tools=[],
                )
                result = await Runner.run(fallback_agent, full_prompt, max_turns=1)
            else:
                raise
        response = result.final_output
        
        processed_response = latex_converter.latex_to_text(response)
        processed_response = fix_markdown_tables(processed_response)
        processed_response = linkify_bare_urls(processed_response)

        text_without_tables, parsed_tables = extract_markdown_tables(processed_response)
        rich_tables = build_rich_tables(parsed_tables) if parsed_tables else []
        
        renderable = Group(Markdown(text_without_tables), *rich_tables) if rich_tables else Markdown(text_without_tables)
        
        print()
        console.print(Panel(renderable, title="Agent", border_style="magenta", style="bold magenta"))
        
        history.append(f"User: {prompt}")
        history.append(f"Assistant: {response}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GPT OSS Tools - CLI and Web UI")
    parser.add_argument("--model", type=str, default="ollama_chat/gpt-oss:20b", help="Model identifier")
    parser.add_argument("--api-key", type=str, default="ollama", help="API key or provider selector (e.g., 'ollama')")
    parser.add_argument("--web", action="store_true", help="Launch the dark-themed web UI instead of CLI")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host for web UI")
    parser.add_argument("--port", type=int, default=7860, help="Port for web UI")

    args = parser.parse_args()

    if args.web:
        try:
            # Import lazily so CLI runs even if FastAPI isn't installed
            from web_ui import run_web_ui
        except Exception as e:
            print("Web UI dependencies missing. Install with: pip install fastapi uvicorn pylatexenc")
            raise
        run_web_ui(args.model, args.api_key, host=args.host, port=args.port)
    else:
        asyncio.run(main(args.model, args.api_key))
