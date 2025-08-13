import uuid
import re
import os
from datetime import datetime, timezone
from typing import Dict, Any
import pytz
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from agents import Agent, Runner
from agents.extensions.models.litellm_model import LitellmModel

from searchTools import web_search, browse_url
from statusTools import get_tool_status, set_current_session_id, set_fallback_session_id, clear_tool_status_for_session_now
from weatherTools import get_location, get_weather
from pythonTools import execute_python
from lightTools import *
from calendarTools import list_calendar_events, create_calendar_event, delete_calendar_event
from taskTools import schedule_task, check_tasks, delete_task
from taskScheduler import TaskScheduler
from pylatexenc.latex2text import LatexNodes2Text
from tableTools import fix_markdown_tables, linkify_bare_urls


latex_converter = LatexNodes2Text()

session_store: Dict[str, Dict[str, Any]] = {}
# Helper: attach current time to the message passed into the agent,
# without changing what the UI displays.
def _attach_current_time(message: str) -> str:
    try:
        eastern = pytz.timezone('America/New_York')
        now_et = datetime.now(eastern).strftime('%Y-%m-%d %I:%M:%S %p %Z')
    except Exception:
        now_et = datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
    try:
        now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    except Exception:
        now_utc = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    prefix = f"Current time: {now_utc} | {now_et}\n\n"
    return prefix + (message or '')



def _is_ollama_tool_template_error(exc: Exception) -> bool:
    text = str(exc)
    return (
        ("template:" in text and "slice index out of range" in text)
        or ("/api/chat" in text and "500" in text and "Ollama" in text)
    )


def build_instructions() -> str:
    current_date = datetime.now().strftime("%A, %Y-%m-%d")
    current_time = datetime.now().strftime("%I:%M %p")
    weekday = datetime.now().strftime("%A")
    date_month= datetime.now().strftime("%B %-d, %Y")
    eastern = pytz.timezone('America/New_York')
    now_et = datetime.now(eastern)
    formatted_time = now_et.strftime('%Y%m%dT%H%M%S')
    return f"""

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
        You don't need to include values in your response, unless the user specifically asks for them.

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
        """


def create_agent(model: str, api_key: str) -> Agent:
    return Agent(
        name="Assistant",
        instructions=build_instructions(),
        model=LitellmModel(model=model, api_key=api_key),
        tools=[get_weather, get_location, web_search, browse_url, execute_python, 
        turn_on_light, turn_off_light, set_light_brightness, set_light_hsv, get_light_state, 
        list_calendar_events, create_calendar_event, delete_calendar_event,
        schedule_task, check_tasks, delete_task],
    )


def process_response_text(response: str) -> str:
    processed_response = latex_converter.latex_to_text(response)
    processed_response = fix_markdown_tables(processed_response)
    processed_response = linkify_bare_urls(processed_response)
    return processed_response


SERVER_MODEL = ""
SERVER_API_KEY = ""

# Inject a message into a given session (used by the background scheduler)
async def _inject_message(session_id: str, user_message: str) -> str:
    if not session_id:
        return "No session id"
    if session_id not in session_store:
        session_store[session_id] = {
            "agent": create_agent(SERVER_MODEL, SERVER_API_KEY),
            "history": [],
            "rev": 0,
        }
    session = session_store[session_id]
    history = session["history"]
    agent: Agent = session["agent"]

    try:
        set_current_session_id(session_id)
        set_fallback_session_id(session_id)
    except Exception:
        pass

    augmented = _attach_current_time(user_message)
    full_prompt = (
        "Previous conversation:\n" + "\n".join(history) + "\n\nCurrent user message: " + augmented
        if history
        else augmented
    )
    result = await Runner.run(agent, full_prompt, max_turns=20)
    response_text = result.final_output
    processed = process_response_text(response_text)

    # Do not show the injected prompt in the UI chat; store as a scheduled user entry
    history.append(f"User (scheduled): {user_message}")
    history.append(f"Iris: {processed}")
    session["rev"] = session.get("rev", 0) + 2
    try:
        # Ensure any active status is cleared immediately when a response is produced
        clear_tool_status_for_session_now(session_id)
    except Exception:
        pass
    return response_text


def create_app() -> FastAPI:
    app = FastAPI(title="Iris", version="1.0.0")

    try:
        assets_dir = os.path.join(os.path.dirname(__file__), "assets")
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    except Exception:
        pass

    @app.get("/_health")
    async def health():
        return {"ok": True}

    @app.on_event("startup")
    async def _start_scheduler():
        # Start background scheduler to check and run due tasks
        app.state.scheduler = TaskScheduler()
        await app.state.scheduler.start(_inject_message)

    @app.get("/api/status")
    async def status_endpoint(session_id: str = ""):
        if not session_id:
            return {"active": False, "label": "", "searching": False, "rev": 0}
        base = get_tool_status(session_id)
        sess = session_store.get(session_id) or {}
        base["rev"] = int(sess.get("rev", 0))
        return base

    # Allow client to explicitly clear any lingering status immediately
    @app.get("/api/status/clear")
    async def status_clear_endpoint(session_id: str = ""):
        try:
            if session_id:
                clear_tool_status_for_session_now(session_id)
            return {"ok": True}
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/api/history")
    async def history_endpoint(session_id: str = ""):
        if not session_id:
            return JSONResponse({"history": [], "rev": 0})
        sess = session_store.get(session_id) or {}
        return JSONResponse({
            "history": sess.get("history", []),
            "rev": int(sess.get("rev", 0)),
        })

    @app.get("/", response_class=HTMLResponse)
    async def index(_: Request):
        return HTMLResponse(content=_INDEX_HTML, status_code=200)

    @app.post("/api/chat")
    async def chat(payload: Dict[str, Any]):
        user_message = (payload.get("message") or "").strip()
        session_id = payload.get("session_id")
        if not user_message:
            return JSONResponse({"error": "Empty message"}, status_code=400)

        if not session_id:
            session_id = str(uuid.uuid4())
        if session_id not in session_store:
            session_store[session_id] = {
                "agent": create_agent(SERVER_MODEL, SERVER_API_KEY),
                "history": [],
                "rev": 0,
            }
        session = session_store[session_id]
        history = session["history"]
        agent: Agent = session["agent"]

        try:
            set_current_session_id(session_id)
            set_fallback_session_id(session_id)
        except Exception:
            pass

        augmented = _attach_current_time(user_message)
        full_prompt = (
            "Previous conversation:\n" + "\n".join(history) + "\n\nCurrent user message: " + augmented
            if history
            else augmented
        )

        try:
            result = await Runner.run(agent, full_prompt, max_turns=20)
        except Exception as e:
            if _is_ollama_tool_template_error(e):
                fallback = Agent(
                    name="Assistant",
                    instructions=build_instructions(),
                    model=LitellmModel(model=SERVER_MODEL, api_key=SERVER_API_KEY),
                    tools=[],
                )
                result = await Runner.run(fallback, full_prompt, max_turns=1)
            else:
                return JSONResponse({"error": f"Agent error: {e}"}, status_code=500)

        response_text = result.final_output
        processed = process_response_text(response_text)

        history.append(f"User: {user_message}")
        history.append(f"Iris: {processed}")
        session["rev"] = session.get("rev", 0) + 2

        # Immediately clear any active status when a response is ready
        try:
            clear_tool_status_for_session_now(session_id)
        except Exception:
            pass

        return JSONResponse({"reply": processed, "session_id": session_id, "rev": session["rev"]})

    @app.post("/api/reset")
    async def reset(payload: Dict[str, Any]):
        existing_id = payload.get("session_id")
        new_id = str(uuid.uuid4())
        session_store[new_id] = {
            "agent": create_agent(SERVER_MODEL, SERVER_API_KEY),
            "history": [],
            "rev": 0,
        }
        if existing_id and existing_id in session_store:
            try:
                del session_store[existing_id]
            except Exception:
                pass
        return JSONResponse({"ok": True, "session_id": new_id})

    return app


def run_web_ui(model: str, api_key: str, host: str = "127.0.0.1", port: int = 7860):
    global SERVER_MODEL, SERVER_API_KEY
    SERVER_MODEL = model
    SERVER_API_KEY = api_key
    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


_INDEX_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover, maximum-scale=1.0" />
  <meta name="theme-color" content="#141a24" />
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
  <meta name="apple-mobile-web-app-title" content="Iris" />
  <meta name="color-scheme" content="dark" />
  <!-- Favicons & PWA -->
  <link rel="apple-touch-icon" sizes="180x180" href="/assets/images/apple-touch-icon.png" />
  <link rel="icon" type="image/png" sizes="32x32" href="/assets/images/favicon-32x32.png" />
  <link rel="icon" type="image/png" sizes="16x16" href="/assets/images/favicon-16x16.png" />
  <link rel="icon" href="/assets/images/favicon.ico" />
  <link rel="manifest" href="/assets/images/site.webmanifest" />
  <link rel="icon" type="image/png" sizes="192x192" href="/assets/images/android-chrome-192x192.png" />
  <link rel="icon" type="image/png" sizes="512x512" href="/assets/images/android-chrome-512x512.png" />
  <title>Iris</title>
  <style>
    :root {
      --bg-0: #0b0f14;
      --bg-1: #141a24;
      --bg-2: #121923;
      --text: #e6edf3;
      --muted: #94a3b8;
      --accent: #a78bfa; /* purple */
      --accent-2: #22d3ee; /* cyan */
      --card: rgba(21, 27, 36, 0.7);
      --border: rgba(148, 163, 184, 0.15);
      --user: #1f2937;
      --assistant: #181f31;
      --shadow: 0 10px 25px rgba(0, 0, 0, 0.35);
    }

    * { box-sizing: border-box; }
    html {
      height: -webkit-fill-available;
      background: linear-gradient(300deg,#0b0f14,#0f141a,#121923,#1b2840) !important;
      background-size: 240% 240% !important;
      animation: gradient-animation 24s ease infinite !important;
    }
    body {
      margin: 0;
      color: var(--text);
      /* Use a solid background that matches the theme to avoid iOS safe-area black fallbacks */
      background: var(--bg-1) !important;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, Helvetica Neue, Arial, "Apple Color Emoji", "Segoe UI Emoji";
      min-height: 100dvh;
      min-height: -webkit-fill-available;
      overflow: hidden;
      overscroll-behavior-y: none;
    }

    /* Subtle texture grid overlay */
    body::after {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background-image:
        linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px);
      background-size: 40px 40px;
      mix-blend-mode: overlay;
      opacity: 0.25;
    }

    /* iOS Safari: avoid white flashes and ensure background paints under UI chrome */
    @supports (-webkit-touch-callout: none) {
      body { background-attachment: scroll; }
    }

    /* Paint the top safe-area explicitly with a static color (no animation) */
    .bg-top-safe {
      position: fixed;
      top: 0; left: 0; right: 0;
      height: env(safe-area-inset-top, 0);
      height: constant(safe-area-inset-top, 0);
      background: var(--bg-1);
      z-index: 1000; /* above header */
      pointer-events: none;
    }

    /* Bottom safe area overlay (static color to match theme) */
    .bg-bottom-safe {
      position: fixed;
      bottom: 0; left: 0; right: 0;
      height: env(safe-area-inset-bottom, 0);
      height: constant(safe-area-inset-bottom, 0);
      background: var(--bg-1);
      z-index: 1000; /* above input bar */
      pointer-events: none;
    }

    .wrap {
      height: 100dvh;
      display: grid;
      grid-template-rows: auto 1fr auto;
      max-width: 1100px;
      width: 100%;
      margin: 0 auto;
    }

    header {
      position: sticky;
      top: 0;
      display: flex;
      align-items: center;
      gap: 12px;
      padding: calc(10px + env(safe-area-inset-top, 0)) 18px 10px 18px;
      background: transparent;
      border-bottom: 1px solid var(--border);
      backdrop-filter: none;
      z-index: 10;
    }

    .logo {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: radial-gradient(circle at 30% 30%, #c0d2f1, #a6b0f7, #8caef7, #a3a5f6);
      background-size: 120% 120%;
      animation: gradient-animation 12s ease infinite, pulse 3s ease-in-out infinite;
      box-shadow: 0 0 25px rgba(163, 165, 246, 0.6), 0 0 25px rgba(192, 210, 241, 0.4);
    }


    @keyframes pulse {
      0%,100% { transform: scale(1); opacity: 0.95; }
      50% { transform: scale(1.08); opacity: 1; }
    }

    h1 {
      font-size: 16px;
      font-weight: 600;
      margin: 0;
      letter-spacing: 0.3px;
    }

    main {
      display: grid;
      grid-template-columns: 1fr;
      padding: 20px;
      gap: 16px;
      overflow: hidden;
    }

    .chat-card {
      display: grid;
      grid-template-rows: 1fr auto;
      overflow: hidden;
      border: 1px solid var(--border);
      border-radius: 16px;
      background: linear-gradient(180deg, rgba(17, 24, 39, 0.65), rgba(17, 24, 39, 0.4));
      box-shadow: var(--shadow);
      backdrop-filter: blur(14px) saturate(140%);
    }

    .messages {
      padding: 18px;
      overflow-y: auto;
      scroll-behavior: smooth;
      padding-bottom: 8px;
      -webkit-overflow-scrolling: touch;
      touch-action: pan-y;
      -ms-overflow-style: none;  /* IE and Edge */
      scrollbar-width: none;     /* Firefox */
    }
    .messages::-webkit-scrollbar { display: none; }

    .message {
      display: grid;
      grid-template-columns: 1fr;
      gap: 8px;
      align-items: flex-start;
      margin-bottom: 16px;
      opacity: 0;
      transform: translateY(8px);
      animation: fadeInUp 260ms ease forwards;
    }

    @keyframes fadeInUp {
      to { opacity: 1; transform: translateY(0); }
    }

    .bubble {
      position: relative;
      padding: 14px 16px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: linear-gradient(180deg, rgba(15, 23, 42, 0.9), rgba(17, 24, 39, 0.75));
    }

    .message.user .bubble {
      background: linear-gradient(180deg, rgba(31, 41, 55, 0.9), rgba(31, 41, 55, 0.75));
    }

    .role { font-size: 12px; color: var(--muted); margin-bottom: 6px; text-transform: none; letter-spacing: 0.06em; }

    .content { color: var(--text); white-space: pre-wrap; line-height: 1.55; overflow-wrap: anywhere; word-break: break-word; }
    .content code { background: rgba(148,163,184,0.15); padding: 0 6px; border-radius: 6px; }
    .content pre { background: #0b1220; border: 1px solid var(--border); border-radius: 10px; padding: 12px; overflow-x: auto; }
    .content a { color: var(--accent-2); text-decoration: none; border-bottom: 1px dotted rgba(34, 211, 238, 0.4); }
    .content a:hover { border-bottom-style: solid; }
    .content h1, .content h2, .content h3, .content h4 { margin: 12px 0 6px; line-height: 1.3; }
    .content h1 { font-size: 1.5rem; }
    .content h2 { font-size: 1.3rem; }
    .content h3 { font-size: 1.15rem; }
    .content ul, .content ol { margin: 8px 0 8px 20px; }
    .content li { margin: 4px 0; }
    .content blockquote { margin: 8px 0; padding: 8px 12px; border-left: 3px solid var(--accent); background: rgba(167, 139, 250, 0.07); }

    /* Table styling for rendered markdown */
    .content table { width: 100%; border-collapse: collapse; margin: 8px 0 2px; }
    .content th, .content td { border: 1px solid var(--border); padding: 8px 10px; text-align: left; }
    .content thead th { background: rgba(148,163,184,0.08); color: var(--text); }
    .content tbody tr:nth-child(even) { background: rgba(148,163,184,0.06); }

    .typing {
      display: inline-flex; gap: 4px; align-items: center;
    }
    .typing .dot {
      width: 6px; height: 6px; border-radius: 50%; background: var(--muted);
      animation: blink 1.2s infinite ease-in-out;
    }
    .typing .dot:nth-child(2) { animation-delay: 0.15s; }
    .typing .dot:nth-child(3) { animation-delay: 0.3s; }
    @keyframes blink { 0%, 80%, 100% { opacity: 0.25; } 40% { opacity: 1; } }

    .input-bar {
      display: grid; grid-template-columns: 1fr auto; gap: 12px;
      padding: 12px; padding-bottom: calc(12px + env(safe-area-inset-bottom, 0));
      border-top: 1px solid var(--border); background: rgba(11, 15, 20, 0.65);
      backdrop-filter: blur(10px) saturate(140%);
    }
    .field { position: relative; }
    textarea {
      resize: none; height: 56px; padding: 14px 16px; border-radius: 12px; border: 1px solid var(--border);
      background: linear-gradient(180deg, rgba(17, 24, 39, 0.8), rgba(17, 24, 39, 0.6)); color: var(--text);
      outline: none; font-size: 14px; line-height: 1.45; box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
    }
    /* Hide textarea scrollbars but keep scroll functionality */
    textarea { overflow: auto; scrollbar-width: none; -ms-overflow-style: none; }
    textarea::-webkit-scrollbar { display: none; }
    /* Hide native placeholder color; we will render a custom shimmering placeholder overlay for better styling */
    textarea::placeholder { color: transparent; }
    textarea::-webkit-input-placeholder { color: transparent; }
    textarea:-ms-input-placeholder { color: transparent; }

/* Hide caret on touch devices when the field is empty and showing the placeholder */
@media (hover: none) and (pointer: coarse) {
  textarea#input:placeholder-shown { caret-color: transparent; }
  textarea#input:placeholder-shown:focus { caret-color: transparent; }
}

    .fake-placeholder {
      position: absolute;
      left: 16px; right: 12px; top: 50%; transform: translateY(-50%);
      font-size: 14px; line-height: 1.45;
      pointer-events: none;
      color: transparent;
      background: linear-gradient(90deg, rgba(148,163,184,0.4) 0%, rgba(230,237,243,0.9) 20%, rgba(148,163,184,0.4) 40%);
      background-size: 200% 100%;
      -webkit-background-clip: text; background-clip: text;
      -webkit-text-fill-color: transparent;
      animation: shimmer 6000ms linear infinite; /* slowed shimmer */
      opacity: 0.8;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    /* Shimmer for "Searching…" status inside the typing bubble */
    .status-shimmer {
      display: inline-block;
      background: linear-gradient(90deg, rgba(148,163,184,0.4) 0%, rgba(230,237,243,0.9) 20%, rgba(148,163,184,0.4) 40%);
      background-size: 200% 100%;
      -webkit-background-clip: text; background-clip: text;
      -webkit-text-fill-color: transparent;
      animation: shimmer 6000ms linear infinite;
    }

    @keyframes shimmer {
      0% { background-position: 200% 0; }
      100% { background-position: -200% 0; }
    }

    
    button {
      height: 56px; padding: 0 18px; border-radius: 12px; border: 1px solid var(--border); cursor: pointer;
      color: #ffffff; font-weight: 600; letter-spacing: 0.3px;
      background: linear-gradient(300deg, #c0d2f1, #a6b0f7, #8caef7, #a3a5f6);
      background-size: 120% 120%;
      animation: gradient-animation 12s ease infinite;
      box-shadow: 0 10px 20px rgba(167, 139, 250, 0.25), 0 6px 16px rgba(34, 211, 238, 0.18);
      transition: transform 160ms ease, box-shadow 200ms ease, filter 200ms ease;
    }
    button:hover { transform: translateY(-1px); filter: brightness(1.05); }
    button:active { transform: translateY(0); }
    button[disabled] { opacity: 0.6; cursor: not-allowed; filter: grayscale(0.2); }

    .ghost-btn {
      height: 36px; padding: 0 12px; margin-left: auto;
      background: transparent;
      color: var(--muted);
      border: 1px solid var(--border);
      border-radius: 10px;
      box-shadow: none;
      transition: background 160ms ease, color 160ms ease, border-color 160ms ease;
    }
    .ghost-btn:hover { background: transparent; color: var(--text); }

    @media (max-width: 720px) {
      body { font-size: 14px; }
      header { gap: 8px; }
      h1 { font-size: 14px; }
      main { padding: 10px; }
      .chat-card { border-radius: 14px; }
      .messages { padding: 10px; padding-bottom: 6px; }
      .message { margin-bottom: 12px; }
      .bubble { padding: 9px 11px; }
      .role { font-size: 11px; letter-spacing: 0.04em; }
      .content { font-size: 13.5px; line-height: 1.45; }
      .content pre { font-size: 12px; padding: 10px; }
      .content code { font-size: 12.5px; }
      textarea { height: 56px; font-size: 16px; padding: 14px 16px; line-height: 1.45; }
      .fake-placeholder { font-size: 16px; left: 12px; right: 10px; }
      button { height: 56px; padding: 0 12px; font-size: 16px; }
      .ghost-btn { height: 30px; padding: 0 10px; font-size: 12px; }
    }
    @media (max-width: 480px) {
      body { font-size: 13px; }
      main { padding: 8px; }
      .messages { padding: 8px; padding-bottom: 4px; }
      .chat-card { border-radius: 12px; }
      .role { font-size: 10px; letter-spacing: 0.03em; }
      .content { font-size: 13px; line-height: 1.4; }
      .content pre { font-size: 11.5px; padding: 8px; }
      .content code { font-size: 12px; }
      textarea { height: 56px; font-size: 16px; padding: 14px 16px; }
      .fake-placeholder { font-size: 16px; left: 10px; right: 8px; }
      button { height: 56px; padding: 0 10px; font-size: 16px; }
    }

    @media (prefers-reduced-motion: reduce) {
      * { animation: none !important; transition: none !important; }
    }
  
/* --- Alignment & sizing fixes for input and send button --- */
.input-bar { grid-template-columns: minmax(0, 1fr) auto; align-items: center; }
.field { width: 100%; }
textarea#input { width: 100%; box-sizing: border-box; }
.input-bar button { box-sizing: border-box; }

/* Keep input bar padding aligned with messages padding on narrow screens */
@media (max-width: 720px) {
  .input-bar { padding: 10px; padding-bottom: calc(10px + env(safe-area-inset-bottom, 0)); }
}
@media (max-width: 480px) {
  .input-bar { padding: 8px; padding-bottom: calc(8px + env(safe-area-inset-bottom, 0)); }
}

/* --- Desktop tweaks: compact input, match send button, and hide cursor on focus --- */
@media (min-width: 721px) {
  /* Match heights and make input slightly more compact */
  .input-bar button { height: 48px; }
  textarea#input { height: 48px; padding-top: 10px; padding-bottom: 10px; }
}

@media (hover: hover) and (pointer: fine) and (min-width: 721px) {
  textarea#input:focus { caret-color: auto; cursor: text; }
}

/* --- Reduce bottom padding for user/assistant bubbles, exclude typing indicator --- */
.message.user:not(.typing) .bubble,
.message.assistant:not(.typing) .bubble { padding-bottom: 8px; }

@media (max-width: 720px) {
  .message.user:not(.typing) .bubble,
  .message.assistant:not(.typing) .bubble { padding-bottom: 7px; }
}
@media (max-width: 480px) {
  .message.user:not(.typing) .bubble,
  .message.assistant:not(.typing) .bubble { padding-bottom: 6px; }
}

/* --- Tighten bottom spacing in chat bubbles --- */
.message.user:not(.typing) .bubble,
.message.assistant:not(.typing) .bubble { padding-bottom: 6px; }

/* Normalize inner element margins so last item doesn't add extra bottom space */
.content p { margin: 0 0 8px; }
.content > :last-child { margin-bottom: 0 !important; }

/* Responsive tweaks */
@media (max-width: 720px) {
  .message.user:not(.typing) .bubble,
  .message.assistant:not(.typing) .bubble { padding-bottom: 5px; }
  .content p { margin-bottom: 6px; }
}
@media (max-width: 480px) {
  .message.user:not(.typing) .bubble,
  .message.assistant:not(.typing) .bubble { padding-bottom: 4px; }
  .content p { margin-bottom: 5px; }
}

/* --- Gentle color-shifted background using existing palette --- */
body { animation: none !important; } /* cancel any previous body bg animations */

/* Two fixed overlays that crossfade very slowly between accent hues */
body::before,
body::after {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  /* Keep it subtle; use existing accent colors only */
  background:
    radial-gradient(1200px 600px at 12% -6%, color-mix(in srgb, var(--accent) 26%, transparent) 0%, transparent 60%),
    radial-gradient(1000px 520px at 112% 12%, color-mix(in srgb, var(--accent-2) 26%, transparent) 0%, transparent 55%);
  opacity: 0.22;
}

/* Layer B swaps the accents so the crossfade feels like a color shift */
body::after {
  background:
    radial-gradient(1200px 600px at 12% -6%, color-mix(in srgb, var(--accent-2) 26%, transparent) 0%, transparent 60%),
    radial-gradient(1000px 520px at 112% 12%, color-mix(in srgb, var(--accent) 26%, transparent) 0%, transparent 55%);
  opacity: 0;
}

/* Slow, smooth crossfade */
@keyframes bgCrossfadeA { 0%, 100% { opacity: 0.24; } 50% { opacity: 0.10; } }
@keyframes bgCrossfadeB { 0%, 100% { opacity: 0.10; } 50% { opacity: 0.24; } }

body::before { animation: bgCrossfadeA 80s ease-in-out infinite; }
body::after  { animation: bgCrossfadeB 80s ease-in-out infinite; }

/* Ensure content paints above overlays */
.wrap, header, main, .chat-card { position: relative; z-index: 1; }

/* Respect user preferences */
@media (prefers-reduced-motion: reduce) {
  body::before, body::after { animation: none !important; opacity: 0.18; }
}

/* Empty chat placeholder */
#messages:empty::before {
  content: "What can I help with?";
  color: #ffffff;
  font-family: "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji";
}

/* Enhanced empty chat placeholder: centered and larger */
#messages:empty {
  position: relative;
  min-height: 240px; /* ensures there's room to center the text */
}

#messages:empty::before {
  content: "What can I help with?";
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 90%;
  text-align: center;
  color: #ffffff;
  font-family: "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji";
  font-size: clamp(24px, 5vw, 40px); /* much larger, responsive */
  line-height: 1.2;
}

/* Animated gradient background */
body.gradient-background {
  background: linear-gradient(300deg,#151b22,#10151b,#18202a,#23314f);
  background-size: 240% 240%;
  animation: gradient-animation 24s ease infinite !important;
  background-attachment: fixed;
}

/* Disable existing overlays when gradient is active */
body.gradient-background::before,
body.gradient-background::after {
  content: none !important;
}

@keyframes gradient-animation {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}

/* Keep chat container static regardless of animated page background */
.chat-card {
  background: var(--assistant) !important; /* #111827 */
  backdrop-filter: none !important;
}

/* Fixed full-viewport gradient layer to ensure safe areas are painted on iOS */
.page-bg {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background: linear-gradient(300deg,#151b22,#10151b,#18202a,#23314f);
  background-size: 240% 240%;
  animation: gradient-animation 24s ease infinite;
}

</style>
</head>
<body class="gradient-background">
  <div class="bg-top-safe"></div>
  <div class="bg-bottom-safe"></div>
  <div class="page-bg"></div>
  <div class="wrap">
    <header>
      <div class="logo"></div>
      <h1>Iris</h1>
      <button id="reset" class="ghost-btn" title="Reset conversation">Reset</button>
    </header>

    <main>
      <div class="chat-card">
        <div id="messages" class="messages" role="log" aria-live="polite"></div>
        <div class="input-bar">
          <div class="field">
            <textarea id="input" placeholder="Ask anything..."></textarea>
            <div id="fakePH" class="fake-placeholder">Ask anything…</div>
          </div>
          <button id="send">Send</button>
        </div>
      </div>
    </main>
  </div>

  <!-- Markdown renderer and sanitizer -->
  <script src="https://cdn.jsdelivr.net/npm/marked@12.0.1/marked.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/dompurify@3.0.6/dist/purify.min.js"></script>
  <script>
    const messagesEl = document.getElementById('messages');
    const inputEl = document.getElementById('input');
    const sendEl = document.getElementById('send');
    const resetEl = document.getElementById('reset');
    const fakePH = document.getElementById('fakePH');
    // --- Mobile caret hider: keep caret hidden on touch when placeholder is visible ---
    const _isTouch = window.matchMedia && matchMedia('(hover: none) and (pointer: coarse)').matches;
    // Desktop detection (fine pointer + hover + wide screens)
    const _isDesktop = window.matchMedia && matchMedia('(hover: hover) and (pointer: fine) and (min-width: 721px)').matches;
    // Track the baseline (original) height on desktop to snap back when content shrinks
    let _desktopBaseHeight = 0;
    function _updateCaret() {
      if (!_isTouch) return;
      inputEl.style.caretColor = inputEl.value ? '' : 'transparent';
    }
    inputEl.addEventListener('focus', _updateCaret);
    inputEl.addEventListener('blur', () => { if (_isTouch) inputEl.style.caretColor = ''; });


      // Vertically center the caret with the placeholder on desktop when single-line
      function alignCaretToCenter() {
        if (!inputEl) return;
        try {
          // Always start from natural metrics
          inputEl.style.lineHeight = '';
          inputEl.style.paddingTop = '';
          inputEl.style.paddingBottom = '';

          // Only apply centering on desktop and when content is a single visual line
          if (!_isDesktop) return;

          const hasNewline = /\n/.test(inputEl.value || '');
          const height = inputEl.clientHeight || 0; // includes padding
          const cs = window.getComputedStyle(inputEl);
          const lineHeightPx = parseFloat(cs.lineHeight);

          if (!height || !isFinite(lineHeightPx) || lineHeightPx <= 0) return;

          // If content would wrap/scroll or contains explicit newline, keep natural layout
          const contentTall = (inputEl.scrollHeight > height + 1) || hasNewline;
          if (contentTall) return;

          // Center single-line vertically by balancing top/bottom padding
          const targetPad = Math.max(0, (height - lineHeightPx) / 2);
          inputEl.style.paddingTop = `${targetPad}px`;
          inputEl.style.paddingBottom = `${targetPad}px`;
          // Lock the computed line-height so centering remains stable
          inputEl.style.lineHeight = `${lineHeightPx}px`;
        } catch (_) {
          // best-effort; ignore failures
        }
      }

      // Re-align on focus
      inputEl.addEventListener('focus', alignCaretToCenter);


    let sessionId = localStorage.getItem('gpt_oss_session');
    if (!sessionId) {
      try {
        sessionId = (crypto && crypto.randomUUID) ? crypto.randomUUID() : 'sess_' + Math.random().toString(36).slice(2);
      } catch (_) {
        sessionId = 'sess_' + Math.random().toString(36).slice(2);
      }
      localStorage.setItem('gpt_oss_session', sessionId);
    }

    function escapeHtml(html) {
      return html
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    }

    function linkify(text) {
      const urlRegex = /(https?:\/\/[\w\-._~:\/?#\[\]@!$&'()*+,;=%]+)/g;
      return text.replace(urlRegex, (url) => `<a href="${url}" target="_blank" rel="noreferrer noopener">${url}</a>`);
    }

    // Markdown rendering with tables using marked + DOMPurify (fallback to basic if libs missing)
    function renderMarkdown(text) {
      if (!text) return '';
      if (window.marked && window.DOMPurify) {
        marked.setOptions({ gfm: true, breaks: true, headerIds: false, mangle: false });
        const html = marked.parse(text);
        return DOMPurify.sanitize(html, { USE_PROFILES: { html: true } });
      }
      // Fallback: minimal rendering
      let safe = escapeHtml(text);
      safe = safe.replace(/```([\s\S]*?)```/g, (m, code) => `<pre><code>${code.replace(/\n/g, '\n')}</code></pre>`);
      safe = safe.replace(/`([^`]+)`/g, (m, code) => `<code>${code}</code>`);
      return linkify(safe);
    }

    function addMessage(role, htmlContent, isTyping=false) {
      const wrap = document.createElement('div');
      wrap.className = `message ${role}`;
      if (isTyping) { wrap.classList.add('typing'); }
      wrap.innerHTML = `
        <div class="bubble">
          <div class="role">${role === 'user' ? 'You' : 'Iris'}</div>
          <div class="content">${isTyping ? `<span class="typing"><span class="dot"></span><span class="dot"></span><span class="dot"></span></span>` : htmlContent}</div>
        </div>
      `;
      messagesEl.appendChild(wrap);
      scrollToBottom();
      return wrap;
    }

    // Track server-side session revision to render scheduled messages
    let lastRev = 0;
    // Background status handling when there is no active typing bubble
    let _bgStatusTimer = null;
    let _bgTypingEl = null;

    function _ensureBgTypingEl() {
      if (_bgTypingEl && document.body.contains(_bgTypingEl)) return _bgTypingEl;
      _bgTypingEl = addMessage('assistant', '', true);
      return _bgTypingEl;
    }

    function _removeBgTypingEl() {
      if (_bgTypingEl && _bgTypingEl.parentNode) {
        _bgTypingEl.parentNode.removeChild(_bgTypingEl);
      }
      _bgTypingEl = null;
    }

    function updateBackgroundStatusFromData(statusData) {
      try {
        const active = !!(statusData && (statusData.active || statusData.searching));
        // If a foreground typing bubble exists, prefer it for status, so remove background bubble if any
        if (_statusTarget && _statusTarget.classList && _statusTarget.classList.contains('typing')) {
          _removeBgTypingEl();
          return;
        }
        if (active) {
          const label = (statusData && statusData.label) || (statusData && statusData.searching ? 'Searching…' : 'Working…');
          const el = _ensureBgTypingEl();
          const content = el.querySelector('.content');
          if (content) content.innerHTML = `<span class="status-shimmer">${escapeHtml(label)}</span>`;
        } else {
          _removeBgTypingEl();
        }
      } catch (_) {}
    }
    let _historyTimer = null;
    async function fetchAndRenderHistoryIfChanged() {
      try {
        const res = await fetch(`/api/status?session_id=${encodeURIComponent(sessionId)}`);
        const data = await res.json();
        const serverRev = parseInt(data && data.rev || 0, 10) || 0;
        if (serverRev > lastRev) {
          const hres = await fetch(`/api/history?session_id=${encodeURIComponent(sessionId)}`);
          const hdata = await hres.json();
          const history = Array.isArray(hdata.history) ? hdata.history : [];
          // Clear and re-render entire history for simplicity and consistency
          messagesEl.innerHTML = '';
          for (const line of history) {
            if (typeof line !== 'string') continue;
            const isUser = line.startsWith('User: ');
            const isScheduled = line.startsWith('User (scheduled): ');
            const isAssistant = line.startsWith('Iris: ');
            if (!isUser && !isAssistant && !isScheduled) continue;
            if (isScheduled) {
              // Hide the injected scheduled prompt; skip rendering this line
              continue;
            }
            const text = line.replace(/^User:\s*/, '').replace(/^Iris:\s*/, '');
            addMessage(isUser ? 'user' : 'assistant', renderMarkdown(text));
          }
          lastRev = serverRev;
        }
        // Always update background status bubble based on latest status
        updateBackgroundStatusFromData(data);
      } catch (e) {
        // ignore fetch errors
      }
    }

    // Status polling to show activity shimmer (e.g., "Searching…", "Adjusting lights…") when tools are active
    let _statusTimer = null;
    let _statusTarget = null; // the current typing bubble being updated
    function _setTypingStatus(el, statusData) {
      // Guard against stale or finalized bubbles
      if (!el || el !== _statusTarget || !el.classList.contains('typing')) return;
      const content = el.querySelector('.content');
      if (!content) return;
      const isActive = !!(statusData && (statusData.active || statusData.searching));
      if (isActive) {
        const label = (statusData && statusData.label) || (statusData && statusData.searching ? 'Searching…' : 'Working…');
        content.innerHTML = `<span class="status-shimmer">${escapeHtml(label)}</span>`;
      } else {
        // Only reset to dots if we are still in typing state; if response already rendered, skip
        if (el.classList.contains('typing')) {
          content.innerHTML = `<span class="typing"><span class="dot"></span><span class="dot"></span><span class="dot"></span></span>`;
        }
      }
    }
    function startStatusPolling(typingEl) {
      stopStatusPolling();
      _statusTarget = typingEl;
      // Immediate check so UI flips to Searching… without delay
      (async () => {
        try {
          const res = await fetch(`/api/status?session_id=${encodeURIComponent(sessionId)}`);
          const data = await res.json();
          _setTypingStatus(typingEl, data);
          // Pick up any newly injected messages
          fetchAndRenderHistoryIfChanged();
          // And reflect background status if applicable (though we have a foreground bubble now)
          updateBackgroundStatusFromData(data);
        } catch (e) {}
      })();
      // Then continue polling
      _statusTimer = setInterval(async () => {
        try {
          const res = await fetch(`/api/status?session_id=${encodeURIComponent(sessionId)}`);
          const data = await res.json();
          _setTypingStatus(typingEl, data);
          fetchAndRenderHistoryIfChanged();
          updateBackgroundStatusFromData(data);
        } catch (e) {
          // ignore errors; keep default typing UI
        }
      }, 600);
    }
    function stopStatusPolling() {
      if (_statusTimer) {
        clearInterval(_statusTimer);
        _statusTimer = null;
      }
      _statusTarget = null;
    }

    function scrollToBottom() {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    async function sendMessage() {
      const text = inputEl.value.trim();
      if (!text) return;

      sendEl.disabled = true;
      const userEl = addMessage('user', renderMarkdown(text));
      inputEl.value = '';
      // Ensure placeholder returns when input is cleared after sending
      fitTextarea();
      fakePH.style.display = inputEl.value ? 'none' : '';
      _updateCaret();

      const typingEl = addMessage('assistant', '', true);
      startStatusPolling(typingEl);

      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text, session_id: sessionId })
        });
        const data = await res.json();
      if (data.session_id && !sessionId) {
          sessionId = data.session_id;
          localStorage.setItem('gpt_oss_session', sessionId);
        }
      if (typeof data.rev === 'number') lastRev = data.rev;
        let reply = data.reply || data.error || 'No response.';
        reply = typeof reply === 'string' ? reply.replace(/\s+$/,'') : reply;
        // Finalize typing bubble before rendering to avoid race with status polling
        stopStatusPolling();
        typingEl.classList.remove('typing');
        typingEl.querySelector('.content').innerHTML = renderMarkdown(reply);
        scrollToBottom();
        // Proactively clear any lingering server-side status once reply is shown
        try { fetch(`/api/status/clear?session_id=${encodeURIComponent(sessionId)}`); } catch (_) {}
      } catch (err) {
        stopStatusPolling();
        typingEl.classList.remove('typing');
        typingEl.querySelector('.content').innerHTML = renderMarkdown('Error: ' + (err?.message || err));
        scrollToBottom();
        try { fetch(`/api/status/clear?session_id=${encodeURIComponent(sessionId)}`); } catch (_) {}
      } finally {
        sendEl.disabled = false;
      }
    }

      function fitTextarea() {
        // Keep textarea height fixed (CSS-controlled) and let content scroll.
        // Clear any inline height that might have been set previously.
        inputEl.style.height = '';
        alignCaretToCenter();
      }

    sendEl.addEventListener('click', sendMessage);
    inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
    inputEl.addEventListener('input', () => {
      fitTextarea();
      fakePH.style.display = inputEl.value ? 'none' : '';
      _updateCaret();
    });

    async function resetConversation() {
      try {
        const res = await fetch('/api/reset', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId })
        });
        const data = await res.json();
        if (data.session_id) {
          sessionId = data.session_id;
          localStorage.setItem('gpt_oss_session', sessionId);
        }
      } catch (e) {
        console.warn('Reset failed:', e);
      }
      messagesEl.innerHTML = '';
      inputEl.value = '';
      fitTextarea();
      // Show placeholder again after reset
      fakePH.style.display = inputEl.value ? 'none' : '';
      _updateCaret();
      lastRev = 0;
      // Fetch and render (likely empty) new session history
      fetchAndRenderHistoryIfChanged();
    }

    resetEl.addEventListener('click', resetConversation);

    // Focus and size input on load
    window.addEventListener('load', () => {
      inputEl.focus();
      fitTextarea();
      fakePH.style.display = inputEl.value ? 'none' : '';
      _updateCaret();
        alignCaretToCenter();
      scrollToBottom();
      if (_isDesktop) {
        // capture baseline after initial layout
        setTimeout(() => { _desktopBaseHeight = inputEl.clientHeight || _desktopBaseHeight || 48; }, 0);
      }
      // Attempt to render any history for existing session
      fetchAndRenderHistoryIfChanged();
      // Also poll periodically so background-scheduled messages appear even when idle
      if (!_historyTimer) {
        _historyTimer = setInterval(fetchAndRenderHistoryIfChanged, 600);
      }
    });
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', () => {
        // keep latest message visible when keyboard shows/hides
        setTimeout(scrollToBottom, 50);
        // re-align caret center when viewport changes
        alignCaretToCenter();
      });
    }
    window.addEventListener('resize', () => {
      if (_isDesktop) {
        _desktopBaseHeight = inputEl.clientHeight || _desktopBaseHeight;
      }
      alignCaretToCenter();
    });
  
// --- Desktop typing redirect: let users type anywhere and it goes to the input ---
(() => {
  const desktop = window.matchMedia('(hover: hover) and (pointer: fine) and (min-width: 721px)');
  if (!desktop.matches) return;
  const interactiveTags = new Set(['INPUT','TEXTAREA','SELECT','BUTTON']);
  document.addEventListener('keydown', (e) => {
    const tag = (document.activeElement && document.activeElement.tagName) || '';
    if (interactiveTags.has(tag)) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;

    const key = e.key;
    const printable = key.length === 1 || key === ' ';

    if (printable || key === 'Backspace' || key === 'Enter') {
      e.preventDefault();
      inputEl.focus();

      const start = inputEl.selectionStart ?? inputEl.value.length;
      const end = inputEl.selectionEnd ?? inputEl.value.length;

      if (key === 'Backspace') {
        if (start === end && start > 0) {
          inputEl.value = inputEl.value.slice(0, start - 1) + inputEl.value.slice(end);
          inputEl.selectionStart = inputEl.selectionEnd = start - 1;
        } else {
          inputEl.value = inputEl.value.slice(0, start) + inputEl.value.slice(end);
          inputEl.selectionStart = inputEl.selectionEnd = start;
        }
      } else if (printable) {
        const ch = key === ' ' ? ' ' : key;
        inputEl.value = inputEl.value.slice(0, start) + ch + inputEl.value.slice(end);
        inputEl.selectionStart = inputEl.selectionEnd = start + ch.length;
      } else if (key === 'Enter') {
        // Insert newline (send behavior remains tied to Enter in the input’s own keydown handler)
        inputEl.value = inputEl.value.slice(0, start) + '\n' + inputEl.value.slice(end);
        inputEl.selectionStart = inputEl.selectionEnd = start + 1;
      }

      // Update placeholder visibility and autosize if those exist
      if (typeof fitTextarea === 'function') fitTextarea();
      if (fakePH) fakePH.style.display = inputEl.value ? 'none' : '';
      _updateCaret();
      inputEl.dispatchEvent(new Event('input', { bubbles: true }));
    }
  });
})();
</script>
</body>
</html>
"""