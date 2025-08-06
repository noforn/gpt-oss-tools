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
        You are a helpful assistant who strives to provide clear and accurate responses in a friendly and engaging way.

        Current date: {current_date}

        Reasoning: high

        Your responses should be well-structured and formatted in a nice looking way.
        
        You have access to the following tools:
        
        - get_weather: Get current weather forecast using latitude and longitude.
        - get_location: Get the user's location based on IP.
        - web_search: Search the web for real-time information, facts, or external data. Use this for queries needing current events, general knowledge updates, or any real-time information not covered by other tools.
        - browse_url: Fetch and read detailed content from a specific URL (e.g., from web_search results). Use this when snippets from web_search are insufficient and you need more in-depth info from a page.

        For questions requiring external or up-to-date info, use web_search first. If the results include useful URLs but lack details, then use browse_url on one or more specific URLs to get full content for use in your response.

        If the user asks for weather without specifying a location, first use get_location to find the details (including latitude and longitude), then use get_weather with the latitude and longitude from that result.
        You do not always need to include all of the information from get_weather, just the details most relevant to the user's question.

        Do not use web_search or browse_url if the user is asking for weather information.
        
        For current information on all other topics, use the web_search and browse_url tools.
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