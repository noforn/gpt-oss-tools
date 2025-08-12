import os
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from agents import function_tool
from statusTools import (
    clear_tool_status,
    mark_checking_tasks,
    mark_deleting_task,
    mark_scheduling_task,
    get_effective_session_id,
)


# Absolute path for the scheduled tasks file next to this module
TASKS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "scheduled_tasks.json"))


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dir(path: str) -> None:
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def _atomic_write_json(path: str, data: Any) -> None:
    _ensure_dir(path)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


def load_tasks() -> List[Dict[str, Any]]:
    """Load the entire task list; returns [] if file missing or invalid."""
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("tasks"), list):
            # Support legacy format {"tasks": [...]}
            return data["tasks"]
        return []
    except FileNotFoundError:
        return []
    except Exception:
        # Corrupted file or parse error: return empty to keep system running
        return []


def save_tasks(tasks: List[Dict[str, Any]]) -> None:
    _atomic_write_json(TASKS_FILE, tasks)


def _parse_vevent_minimal(vevent: str) -> Tuple[bool, Optional[str]]:
    """Very light VEVENT validation: require a DTSTART line with a value."""
    try:
        lines = [ln.strip() for ln in (vevent or "").splitlines() if ln.strip()]
        if not lines:
            return False, "Empty VEVENT"
        has_dtstart = any(ln.startswith("DTSTART") and ":" in ln for ln in lines)
        if not has_dtstart:
            return False, "VEVENT missing DTSTART"
        return True, None
    except Exception as e:
        return False, f"Invalid VEVENT: {e}"


@function_tool
def schedule_task(prompt: str, vevent: str, session_id: str = "") -> Dict[str, Any]:
    """
    Schedule a task for later execution.

    Required:
    - prompt: str — the instructions to execute at the scheduled time
    - vevent: str — an iCalendar VEVENT snippet (must include DTSTART; optional RRULE for recurrence)

    Optional:
    - session_id: str — the target chat session; defaults to the current session if omitted
    """
    mark_scheduling_task()
    try:
        ok, err = _parse_vevent_minimal(vevent)
        if not ok:
            return {"status": "error", "message": err or "Invalid VEVENT"}

        sid = (session_id or "").strip() or (get_effective_session_id() or "")
        if not sid:
            return {"status": "error", "message": "No session_id available to associate with the task."}

        tasks = load_tasks()
        task_id = uuid.uuid4().hex

        task = {
            "id": task_id,
            "session_id": sid,
            "prompt": prompt,
            "vevent": vevent,
            "created_at": _now_iso_utc(),
            "last_run_at": None,
            "completed": False,
            "deleted": False,
        }
        tasks.append(task)
        save_tasks(tasks)

        public_task = {k: v for k, v in task.items() if k != "deleted"}
        return {"status": "success", "message": "Task scheduled.", "task": public_task, "tasks_file": TASKS_FILE}
    finally:
        clear_tool_status()


@function_tool
def check_tasks() -> Dict[str, Any]:
    """
    List all known tasks and a coarse status for each.

    Status rules:
    - completed: True for one-off tasks that already ran, or tasks explicitly marked completed by the scheduler.
    - upcoming: Otherwise (including future one-offs and recurring tasks).
    """
    mark_checking_tasks()
    try:
        tasks = load_tasks()
        visible = [t for t in tasks if not t.get("deleted")]
        out = []
        for t in visible:
            status = "completed" if t.get("completed") else "upcoming"
            out.append({
                "id": t.get("id"),
                "session_id": t.get("session_id"),
                "prompt": t.get("prompt"),
                "vevent": t.get("vevent"),
                "created_at": t.get("created_at"),
                "last_run_at": t.get("last_run_at"),
                "status": status,
            })
        return {"status": "success", "tasks": out, "count": len(out)}
    finally:
        clear_tool_status()


@function_tool
def delete_task(task_id: str) -> Dict[str, Any]:
    """
    Delete a scheduled task by its id.
    """
    mark_deleting_task()
    try:
        tasks = load_tasks()
        new_tasks: List[Dict[str, Any]] = []
        found = False
        for t in tasks:
            if t.get("id") == task_id and not t.get("deleted"):
                found = True
                # Hard delete by skipping
                continue
            new_tasks.append(t)
        if not found:
            return {"status": "error", "message": f"Task '{task_id}' not found."}

        save_tasks(new_tasks)
        return {"status": "success", "message": f"Task '{task_id}' deleted.", "remaining": len(new_tasks)}
    finally:
        clear_tool_status()


