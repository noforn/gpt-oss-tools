import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from agents import function_tool
from rich.console import Console
from contextvars import ContextVar
from typing import Dict, Any, Optional
import time
 

console = Console()

#
# Lightweight per-session tool status so the UI can show "Searching…" while tools run.
#
# The FastAPI layer will set the current session id via set_current_session_id()
# before invoking the agent. Tools read it from a ContextVar and update status.
#
_current_session_id: ContextVar[Optional[str]] = ContextVar("_current_session_id", default=None)
_fallback_session_id: Optional[str] = None  # used when tools run in worker threads where ContextVar doesn't propagate
_session_tool_status: Dict[str, Dict[str, Any]] = {}
_STATUS_LINGER_SECONDS: float = 1.2

def set_current_session_id(session_id: str) -> None:
    """Set the current session id for subsequent tool calls (context-local)."""
    _current_session_id.set(session_id)

def set_fallback_session_id(session_id: str) -> None:
    """Set a process-wide fallback session id for tool calls in worker threads."""
    global _fallback_session_id
    _fallback_session_id = session_id

def _get_effective_session_id() -> Optional[str]:
    sid = _current_session_id.get()
    return sid or _fallback_session_id

def _mark_searching() -> None:
    session_id = _get_effective_session_id()
    if not session_id:
        return
    now = time.time()
    prev = _session_tool_status.get(session_id) or {}
    prev.update({
        "searching": True,
        "updated_at": now,
        "linger_until": now + _STATUS_LINGER_SECONDS,
    })
    _session_tool_status[session_id] = prev

def _clear_status() -> None:
    session_id = _get_effective_session_id()
    if not session_id:
        return
    now = time.time()
    prev = _session_tool_status.get(session_id) or {}
    prev.update({
        "searching": False,
        "updated_at": now,
        "linger_until": now + _STATUS_LINGER_SECONDS,
    })
    _session_tool_status[session_id] = prev

def get_tool_status(session_id: str) -> Dict[str, Any]:
    """Return lightweight status info for a given session id."""
    status = _session_tool_status.get(session_id) or {}
    now = time.time()
    searching = bool(status.get("searching", False))
    if not searching:
        linger_until = float(status.get("linger_until", 0.0) or 0.0)
        if linger_until > now:
            searching = True
    return {"searching": searching}

@function_tool
def web_search(query: str):
    """Search the web for a given query and return summarized results.
    
    Args:
        query (str): The search query.
    
    Returns:
        str: Summarized search results or error message.
    """
    console.print(f"\nPerforming web search for: {query}", style="dim blue")
    _mark_searching()
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
    finally:
        _clear_status()

@function_tool
def browse_url(url: str):
    """Fetch and summarize the content of a webpage with static fetch and automatic JS fallback.

    Returns:
        str: Summarized text content or a clear error message.
    """
    retries = 2
    timeout_seconds = 10
    proxy = None
    console.print(f"\nBrowsing URL: {url}", style="dim blue")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.google.com/'
    }
    block_keywords = ["captcha", "blocked", "access denied", "enable javascript", "robot check"]

    def summarize_text(text: str) -> str:
        text = text.strip()
        return (text[:2000] + '...') if len(text) > 2000 else text

    _mark_searching()
    last_err = None
    try:
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

        if last_err is not None:
            try:
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

        return f"Failed to fetch {url}: {last_err}"
    finally:
        _clear_status()