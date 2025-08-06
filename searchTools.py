import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from agents import function_tool
from rich.console import Console

console = Console()

@function_tool
def web_search(query: str):
    """Search the web for a given query and return summarized results.
    
    Args:
        query (str): The search query.
    
    Returns:
        str: Summarized search results or error message.
    """
    console.print(f"\nPerforming web search for: {query}", style="dim blue")
    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=5)
        if not results:
            return "No results found."
        
        summary = "Web search results:\n"
        for i, res in enumerate(results):
            title = res.get('title', 'No title')
            url = res.get('href', 'No URL')
            snippet = res.get('body', 'No snippet')[:200]
            summary += f"{i+1}. {title}\n   URL: {url}\n   Snippet: {snippet}\n\n"
        return summary
    except Exception as e:
        return f"Oops! : {str(e)}"

@function_tool
def browse_url(url: str):
    """Fetch and summarize the content of a webpage from a given URL.
    
    Args:
        url (str): The URL of the webpage to browse.
    
    Returns:
        str: Summarized text content from the page or error message.
    """
    console.print(f"\nBrowsing URL: {url}", style="dim blue")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        for element in soup(['script', 'style', 'nav', 'footer', 'header']):
            element.decompose()
        text = ' '.join(soup.stripped_strings)
        summary = text[:2000] + '...' if len(text) > 2000 else text
        return f"Content from {url}:\n{summary}"
    except Exception as e:
        return f"Oops! : {str(e)}"