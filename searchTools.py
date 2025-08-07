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
    """Fetch and summarize the content of a webpage with static fetch and automatic JS fallback.

    Returns:
        str: Summarized text content or a clear error message.
    """
    retries = 2
    timeout_seconds = 10
    proxy = None
    console.print(f"\nBrowsing URL: {url} (auto JS fallback)", style="dim blue")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.google.com/'
    }
    block_keywords = ["captcha", "blocked", "access denied", "enable javascript", "robot check"]

    def summarize_text(text: str) -> str:
        text = text.strip()
        return (text[:2000] + '...') if len(text) > 2000 else text

    # 1) Try static HTML fetch with retries
    last_err = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=timeout_seconds,
                proxies={"http": proxy, "https": proxy} if proxy else None,
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            for element in soup(['script', 'style', 'nav', 'footer', 'header']):
                element.decompose()
            text = ' '.join(soup.stripped_strings)
            lowered = text.lower()
            if len(text) < 100 or any(k in lowered for k in block_keywords):
                last_err = Exception("Static fetch appears blocked or content too short")
            else:
                return f"Content from {url}:\n{summarize_text(text)}"
        except Exception as e:
            last_err = e
        # no sleep/backoff to keep it simple here

    # 2) Optionally try JS rendering with Playwright if requested or static failed
    if last_err is not None:
        try:
            # Import lazily so environments without Playwright don't fail at import time
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                launch_kwargs = {"headless": True}
                if proxy:
                    launch_kwargs["proxy"] = {"server": proxy}
                browser = p.chromium.launch(**launch_kwargs)
                context = browser.new_context(
                    user_agent=headers['User-Agent'],
                    locale='en-US'
                )
                page = context.new_page()
                page.goto(url, timeout=timeout_seconds * 1000, wait_until='domcontentloaded')
                # Try to settle for network idle; ignore timeout to still capture content
                try:
                    page.wait_for_load_state('networkidle', timeout=timeout_seconds * 1000)
                except Exception:
                    pass
                html = page.content()
                context.close()
                browser.close()

            soup = BeautifulSoup(html, 'html.parser')
            for element in soup(['script', 'style', 'nav', 'footer', 'header']):
                element.decompose()
            text = ' '.join(soup.stripped_strings)
            lowered = text.lower()
            if len(text) < 100 or any(k in lowered for k in block_keywords):
                return f"All methods yielded limited content for {url}. Try a proxy or different URL."
            return f"Content from {url}:\n{summarize_text(text)}"
        except Exception as e:
            return (
                f"JS rendering unavailable or failed for {url}: {e}\n"
                f"Hint: Install Playwright with 'pip install playwright' and run 'playwright install'."
            )

    # Fallback: return last error from static path
    return f"Failed to fetch {url}: {last_err}"