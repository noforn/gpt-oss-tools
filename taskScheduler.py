import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional
try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - fallback for older Python
    try:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    except Exception:
        ZoneInfo = None  # type: ignore

from taskTools import load_tasks, save_tasks
from statusTools import (
    set_current_session_id,
    set_fallback_session_id,
    mark_running_scheduled_task,
    clear_tool_status,
    clear_tool_status_for_session_now,
)


DEFAULT_CHECK_INTERVAL_SECONDS = 5
DEFAULT_DUE_TOLERANCE_SECONDS = 30


def _parse_dt_value(value: str, tzid: Optional[str]) -> datetime:
    """
    Parse a DTSTART/UNTIL value from iCalendar-like strings.
    Supports:
    - YYYYMMDDTHHMMSSZ
    - YYYYMMDDTHHMMSS
    - YYYYMMDDTHHMM
    - YYYYMMDD
    """
    v = (value or "").strip()

    def _attach_tz(dt: datetime) -> datetime:
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc)
        if tzid and ZoneInfo is not None:
            try:
                return dt.replace(tzinfo=ZoneInfo(tzid)).astimezone(timezone.utc)
            except Exception:
                pass
        # Fallbacks when ZoneInfo is unavailable or TZID invalid
        try:
            # Prefer server's local timezone to better approximate TZID
            local_tz = datetime.now().astimezone().tzinfo
            if local_tz is not None:
                return dt.replace(tzinfo=local_tz).astimezone(timezone.utc)
        except Exception:
            pass
        # Last resort: assume UTC
        return dt.replace(tzinfo=timezone.utc)

    if v.endswith("Z"):
        for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%MZ"):
            try:
                dt = datetime.strptime(v, fmt).replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                pass
        v = v[:-1]

    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M", "%Y%m%d"):
        try:
            dt = datetime.strptime(v, fmt)
            return _attach_tz(dt)
        except Exception:
            continue
    try:
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            return _attach_tz(dt)
        return dt.astimezone(timezone.utc)
    except Exception:
        raise ValueError(f"Unrecognized datetime format: {value}")


def _parse_rrule(rrule: str) -> Dict[str, Any]:
    body = rrule.split(":", 1)[1] if ":" in rrule else rrule
    parts: Dict[str, Any] = {}
    for kv in body.split(";"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            parts[k.strip().upper()] = v.strip()
    if "INTERVAL" in parts:
        try:
            parts["INTERVAL"] = int(parts["INTERVAL"])
        except Exception:
            parts["INTERVAL"] = 1
    else:
        parts["INTERVAL"] = 1
    if "COUNT" in parts:
        try:
            parts["COUNT"] = int(parts["COUNT"])
        except Exception:
            parts["COUNT"] = None
    return parts


def parse_vevent(vevent: str) -> Dict[str, Any]:
    lines = [ln.strip() for ln in (vevent or "").splitlines() if ln.strip()]
    tzid = None
    dtstart_val = None
    rrule = None
    for ln in lines:
        if ln.startswith("DTSTART"):
            if ":" not in ln:
                continue
            head, dtval = ln.split(":", 1)
            if ";TZID=" in head:
                try:
                    tzid = head.split(";TZID=", 1)[1]
                except Exception:
                    tzid = None
            dtstart_val = dtval.strip()
        elif ln.startswith("RRULE"):
            rrule = _parse_rrule(ln)
    if not dtstart_val:
        raise ValueError("VEVENT missing DTSTART")
    start_utc = _parse_dt_value(dtstart_val, tzid)
    return {"start_utc": start_utc, "rrule": rrule}


def _add_months(dt: datetime, months: int) -> datetime:
    y = dt.year + (dt.month - 1 + months) // 12
    m = (dt.month - 1 + months) % 12 + 1
    # Days per month with basic leap year check
    dim = [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    d = min(dt.day, dim[m - 1])
    return dt.replace(year=y, month=m, day=d)


def _next_run_after(start_utc: datetime, rrule: Optional[Dict[str, Any]], after: datetime) -> Optional[datetime]:
    if after.tzinfo is None:
        after = after.replace(tzinfo=timezone.utc)
    candidate = start_utc
    idx = 0
    if not rrule:
        return candidate if candidate > after else None

    freq = (rrule.get("FREQ") or "DAILY").upper()
    interval = int(rrule.get("INTERVAL") or 1)
    count_limit = rrule.get("COUNT")
    until_raw = rrule.get("UNTIL")
    until_utc = _parse_dt_value(until_raw, None) if until_raw else None

    while candidate <= after:
        idx += 1
        if freq == "HOURLY":
            candidate = candidate + timedelta(hours=interval)
        elif freq == "DAILY":
            candidate = candidate + timedelta(days=interval)
        elif freq == "WEEKLY":
            candidate = candidate + timedelta(weeks=interval)
        elif freq == "MONTHLY":
            candidate = _add_months(candidate, interval)
        elif freq == "YEARLY":
            candidate = candidate.replace(year=candidate.year + interval)
        else:
            return None

        if count_limit is not None and idx >= count_limit:
            return None
        if until_utc and candidate > until_utc:
            return None

    return candidate


class TaskScheduler:
    def __init__(self, check_interval: int = DEFAULT_CHECK_INTERVAL_SECONDS, due_tolerance: int = DEFAULT_DUE_TOLERANCE_SECONDS) -> None:
        self.check_interval = check_interval
        self.due_tolerance = due_tolerance
        self._task: Optional[asyncio.Task] = None
        self._stopped = asyncio.Event()

    async def start(self, inject_callback: Callable[[str, str], "asyncio.Future"]) -> None:
        if self._task and not self._task.done():
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._run_loop(inject_callback))

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._stopped.set()
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass

    async def _run_loop(self, inject_callback: Callable[[str, str], "asyncio.Future"]) -> None:
        while not self._stopped.is_set():
            try:
                await self._tick(inject_callback)
            except Exception:
                pass
            await asyncio.sleep(self.check_interval)

    async def _tick(self, inject_callback: Callable[[str, str], "asyncio.Future"]) -> None:
        tasks = load_tasks()
        changed = False
        now = datetime.now(timezone.utc)
        for t in tasks:
            if t.get("deleted"):
                continue

            vevent = t.get("vevent") or ""
            try:
                parsed = parse_vevent(vevent)
            except Exception:
                continue
            start_utc = parsed["start_utc"]
            rrule = parsed.get("rrule")

            last_run_iso = t.get("last_run_at")
            last_run = datetime.fromisoformat(last_run_iso) if last_run_iso else None
            if last_run and last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=timezone.utc)

            if not rrule and t.get("completed"):
                continue

            after = last_run or (start_utc - timedelta(seconds=1))
            next_run = _next_run_after(start_utc, rrule, after)
            if not next_run:
                if not rrule and not t.get("completed"):
                    if last_run is not None:
                        t["completed"] = True
                        changed = True
                continue

            # Run tasks that are due now or overdue and haven't run at this occurrence
            if now >= next_run:
                sid = (t.get("session_id") or "").strip()
                if sid:
                    try:
                        set_current_session_id(sid)
                        set_fallback_session_id(sid)
                    except Exception:
                        pass
                prompt = t.get("prompt") or ""
                try:
                    # Mark status for UI while we inject
                    mark_running_scheduled_task()
                    await inject_callback(sid, prompt)
                    clear_tool_status()
                    # Record last_run as the scheduled timestamp for traceability
                    t["last_run_at"] = next_run.isoformat()
                    if not rrule:
                        t["completed"] = True
                    changed = True
                    # Clear any lingering status after assistant response injection
                    try:
                        if sid:
                            clear_tool_status_for_session_now(sid)
                    except Exception:
                        pass
                except Exception:
                    pass

        if changed:
            save_tasks(tasks)


