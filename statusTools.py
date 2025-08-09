import time
from typing import Dict, Any, Optional
from contextvars import ContextVar


#
# Centralized tool status management
#
_current_session_id: ContextVar[Optional[str]] = ContextVar("_current_session_id", default=None)
_fallback_session_id: Optional[str] = None
_session_tool_status: Dict[str, Dict[str, Any]] = {}
_STATUS_LINGER_SECONDS: float = 1.2


def set_current_session_id(session_id: str) -> None:
    """Bind a session id for the current context so tools can report status."""
    _current_session_id.set(session_id)


def set_fallback_session_id(session_id: str) -> None:
    """Set a process-wide fallback id for worker threads where ContextVar may not propagate."""
    global _fallback_session_id
    _fallback_session_id = session_id


def _get_effective_session_id() -> Optional[str]:
    sid = _current_session_id.get()
    return sid or _fallback_session_id


def _mark_status(label: str, activity_type: str) -> None:
    """Generic status setter for a session with a human-friendly label."""
    session_id = _get_effective_session_id()
    if not session_id:
        return
    now = time.time()
    prev = _session_tool_status.get(session_id) or {}
    prev.update({
        "active": True,
        "label": label,
        "type": activity_type,
        # Maintain legacy key for older UI clients
        "searching": activity_type == "search",
        "updated_at": now,
        "linger_until": now + _STATUS_LINGER_SECONDS,
    })
    _session_tool_status[session_id] = prev


def clear_tool_status() -> None:
    """Clear current status (with linger) for the effective session."""
    session_id = _get_effective_session_id()
    if not session_id:
        return
    now = time.time()
    prev = _session_tool_status.get(session_id) or {}
    prev.update({
        "active": False,
        # Keep previous label/type so the linger period shows the same text
        # Maintain legacy key for older UI clients
        "searching": prev.get("type") == "search" and False,
        "updated_at": now,
        "linger_until": now + _STATUS_LINGER_SECONDS,
    })
    _session_tool_status[session_id] = prev


def get_tool_status(session_id: str) -> Dict[str, Any]:
    """Return lightweight status info for a given session id for the UI."""
    status = _session_tool_status.get(session_id) or {}
    now = time.time()
    linger_until = float(status.get("linger_until", 0.0) or 0.0)
    active_raw = bool(status.get("active", False))
    active = active_raw or (linger_until > now)
    label = status.get("label") or ("Searching…" if status.get("type") == "search" else "Working…")
    # Legacy: only report searching=true for search activity
    legacy_searching = active and (status.get("type") == "search")
    return {"active": active, "label": label, "searching": legacy_searching}


def mark_searching() -> None:
    _mark_status("Searching…", "search")


def mark_adjusting_lights() -> None:
    """Public helper for light tools to mark status as adjusting lights."""
    _mark_status("Adjusting lights…", "lights")


def mark_working_with_calendar() -> None:
    _mark_status("Working with Calendar…", "calendar")

def mark_checking_location() -> None:
    _mark_status("Checking location…", "location")

def mark_getting_weather() -> None:
    _mark_status("Getting weather…", "weather")