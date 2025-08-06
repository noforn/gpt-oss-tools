import asyncio
import requests
from agents import Agent, Runner, function_tool, set_tracing_disabled
from agents.extensions.models.litellm_model import LitellmModel
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from termcolor import colored
from searchTools import web_search, browse_url
from weatherTools import get_location, get_weather
from datetime import datetime

set_tracing_disabled(True)

console = Console()

current_date = datetime.now().strftime("%Y-%m-%d")

async def main(model: str, api_key: str):
    agent = Agent(
        name="Assistant",
        instructions="""

        # Identity

        You are a helpful assistant who strives to provide clear, accurate responses in a friendly and engaging way.

        Knowledge cutoff: 2024-06
        Current date: {current_date}
        Reasoning: high
        
        Your responses should be well-structured and formatted for readability, using markdown elements like headings, bullet points, bold text, and code blocks where appropriate to enhance clarity and organization.

        Always ensure your reponses sound natural and use proper grammar, especially when using tables.
                        
        # Tools
        
        You have access to the following tools:

        get_weather: Retrieves the current weather forecast using latitude and longitude as inputs.
        get_location: Determines the user's location (including latitude and longitude) based on their IP address.
        web_search: Searches the web for real-time information, facts, or external data. Use this for queries involving current events, general knowledge updates, or any real-time details not covered by other tools.
        browse_url: Fetches and reads detailed content from a specific URL (e.g., from web_search results). Use this when web_search snippets are insufficient and you need in-depth information from a page.

        # General Tool Usage Guidelines

        For questions requiring external or up-to-date information, start with web_search. If results include useful URLs but lack sufficient details, follow up with browse_url on one or more specific URLs to gather full content for your response.
        For all non-weather topics needing current information, rely on web_search and browse_url.

        # Weather-Specific Instructions:

        If the user asks for weather without specifying a location, first use get_location to obtain the details (including latitude and longitude), then use get_weather with those coordinates.
        In your response, include only the most relevant weather details based on the user's question—do not provide all available information unless requested.
        Do not use web_search or browse_url for weather-related queries; handle them exclusively with get_location and get_weather as needed.
        """,
        model=LitellmModel(model=model, api_key=api_key),
        tools=[get_weather, get_location, web_search, browse_url],
    )

    history = []
    print(colored("Chat started\ntype 'bye' to quit", "dark_grey"))

    while True:
        prompt = input(colored("\nYou: ", "blue"))
        if prompt.lower() == 'bye':
            print(colored("\nSee you later!", "magenta"))
            break
        
        full_prompt = "Previous conversation:\n" + "\n".join(history) + "\n\nCurrent user message: " + prompt if history else prompt
        
        result = await Runner.run(agent, full_prompt)
        response = result.final_output
        
        print()
        console.print(Panel(Markdown(response), title="Agent", border_style="magenta", style="bold magenta"))
        
        history.append(f"User: {prompt}")
        history.append(f"Assistant: {response}")

if __name__ == "__main__":
    asyncio.run(main("ollama_chat/gpt-oss:20b", "ollama"))