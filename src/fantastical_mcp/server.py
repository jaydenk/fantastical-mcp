"""FastMCP server with tool definitions for Fantastical calendar."""

import logging
import os
from datetime import datetime, timedelta, timezone

from fastmcp import FastMCP

from .db import FantasticalDB, find_database_path
from .formatters import (
    format_availability,
    format_calendars,
    format_event_detail,
    format_events_by_calendar,
    format_events_by_date,
)
from .json_encoders import encode_event, encode_event_detail
from .url_scheme import create_event_url, execute_url, show_date_url

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TRANSPORT = os.environ.get("FANTASTICAL_MCP_TRANSPORT", "stdio")
HTTP_HOST = os.environ.get("FANTASTICAL_MCP_HOST", "127.0.0.1")
HTTP_PORT = int(os.environ.get("FANTASTICAL_MCP_PORT", "8000"))

MAX_DAYS = 365
MAX_LIMIT = 200

mcp = FastMCP("Fantastical")

_db: FantasticalDB | None = None


def _get_db() -> FantasticalDB:
    global _db
    if _db is None:
        _db = FantasticalDB(find_database_path())
    return _db


@mcp.tool
async def get_today() -> str:
    """Get all calendar events for today, grouped by calendar."""
    db = _get_db()
    now = datetime.now(timezone.utc)
    start = now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    events = db.get_events_in_range(
        start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    )
    if not events:
        return "No events today."
    header = f"Today — {start.strftime('%A %-d %B %Y')}\n\n"
    return header + format_events_by_calendar(events)


@mcp.tool
async def get_upcoming(days: int = 7) -> str:
    """Get calendar events for the next N days, grouped by date.

    Args:
        days: Number of days to look ahead (default 7).
    """
    days = min(days, MAX_DAYS)
    db = _get_db()
    now = datetime.now(timezone.utc)
    start = now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days)
    events = db.get_events_in_range(
        start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    )
    if not events:
        return f"No events in the next {days} days."
    return format_events_by_date(events)


@mcp.tool
async def get_calendars() -> str:
    """List all calendars with their event counts."""
    db = _get_db()
    calendars = db.get_calendars()
    return format_calendars(calendars)


@mcp.tool
async def get_event(event_id: int) -> str:
    """Get full details for a specific event by its ID.

    Args:
        event_id: The event ID (shown in parentheses in event listings).
    """
    db = _get_db()
    event = db.get_event(event_id)
    if not event:
        return f"No event found with ID {event_id}."
    return format_event_detail(event)


@mcp.tool
async def search_events(query: str, limit: int = 20) -> str:
    """Search events by title, location, notes, or attendees.

    Args:
        query: Search term (supports FTS5 syntax: AND, OR, NOT, quotes for phrases).
        limit: Maximum number of results (default 20).
    """
    limit = min(limit, MAX_LIMIT)
    db = _get_db()
    events = db.search_events(query, limit=limit)
    if not events:
        return f"No events found matching '{query}'."
    return format_events_by_date(events)


@mcp.tool
async def get_events_by_calendar(calendar: str, days: int = 30) -> str:
    """Get events from a specific calendar.

    Args:
        calendar: Calendar name (e.g. "Work", "Personal"). Use get_calendars to see available names.
        days: Number of days to look ahead (default 30).
    """
    days = min(days, MAX_DAYS)
    db = _get_db()
    events = db.get_events_by_calendar(calendar, days=days)
    if not events:
        return f"No events in '{calendar}' for the next {days} days."
    return format_events_by_date(events)


@mcp.tool
async def get_availability(date: str, calendars: list[str] | None = None) -> str:
    """Show free/busy time slots for a specific date.

    Args:
        date: Date in YYYY-MM-DD format.
        calendars: Optional list of calendar names to check. If omitted, checks all calendars.
    """
    db = _get_db()
    try:
        naive = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return f"Invalid date format: {date}. Use YYYY-MM-DD."

    # Anchor to local midnight, then convert to UTC for the database query.
    local_start = naive.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    local_end = local_start + timedelta(days=1)
    start = local_start.astimezone(timezone.utc)
    end = local_end.astimezone(timezone.utc)

    all_events = db.get_events_in_range(start, end)
    if calendars:
        cal_set = {c.lower() for c in calendars}
        all_events = [
            e for e in all_events
            if e.get("calendar", "").lower() in cal_set
        ]
    events = all_events

    return format_availability(events, date)


@mcp.tool
async def get_recurring(
    calendar: str | None = None,
    limit: int = 50,
) -> str:
    """List upcoming recurring events, optionally filtered by calendar.

    Useful for understanding the regular schedule (standups, focus blocks, etc.).

    Args:
        calendar: Optional calendar name to filter by. Use get_calendars to see available names.
        limit: Maximum number of results (default 50).
    """
    limit = min(limit, MAX_LIMIT)
    db = _get_db()
    events = db.get_recurring_events(calendar_name=calendar, limit=limit)
    if not events:
        msg = "No upcoming recurring events"
        if calendar:
            msg += f" in '{calendar}'"
        return msg + "."
    return format_events_by_calendar(events)


@mcp.tool
async def get_invitations(limit: int = 20) -> str:
    """List pending event invitations that need a response.

    Args:
        limit: Maximum number of results (default 20).
    """
    limit = min(limit, MAX_LIMIT)
    db = _get_db()
    events = db.get_pending_invitations(limit=limit)
    if not events:
        return "No pending invitations."
    return format_events_by_date(events)


@mcp.tool
async def get_recent(limit: int = 10) -> str:
    """Show the most recently added or synced calendar events.

    Useful for seeing what's new on the calendar without knowing specific dates.

    Args:
        limit: Maximum number of results (default 10).
    """
    limit = min(limit, MAX_LIMIT)
    db = _get_db()
    events = db.get_recent_events(limit=limit)
    if not events:
        return "No recent events."
    return format_events_by_date(events)


@mcp.tool
async def create_event(
    sentence: str,
    calendar: str | None = None,
    add_immediately: bool = False,
) -> str:
    """Create a new event in Fantastical using natural language.

    Fantastical's parser handles dates, times, locations, and recurrence naturally.
    Examples: "Lunch with Sara tomorrow at noon at The Crafers Hotel",
    "Weekly team standup every Monday at 9am".

    Args:
        sentence: Natural language event description.
        calendar: Optional calendar name to create the event in.
        add_immediately: If True, add without showing confirmation UI (default False).
    """
    url = create_event_url(sentence, calendar=calendar, add_immediately=add_immediately)
    execute_url(url, background=True)
    msg = f"Created event: {sentence}"
    if calendar:
        msg += f" (in {calendar})"
    if not add_immediately:
        msg += "\nFantastical is showing the event for confirmation."
    return msg


@mcp.tool
async def get_today_json() -> dict:
    """Machine-readable variant of get_today.

    Returns today's events as a structured dict so programmatic clients
    (dashboards, automations) don't have to parse the pretty-printed text
    output. Event times are ISO-8601 strings in the event's original
    timezone.

    Response shape::

        {
          "now": ISO-8601 string (current local time),
          "timezone": IANA name (e.g. "Australia/Adelaide"),
          "events": [{id, title, calendar, start, end, all_day,
                      location, recurring, attendees_count}, ...]
        }
    """
    db = _get_db()
    now = datetime.now(timezone.utc)
    start = now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    events = db.get_events_in_range(
        start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    )
    local_tz = now.astimezone().tzinfo
    return {
        "now": now.astimezone().isoformat(),
        "timezone": str(local_tz) if local_tz else "",
        "events": [encode_event(e) for e in events],
    }


@mcp.tool
async def get_upcoming_json(days: int = 7) -> dict:
    """Machine-readable variant of get_upcoming.

    Args:
        days: Number of days to look ahead (default 7).

    Response shape mirrors get_today_json but covers the next *days* days.
    """
    days = min(days, MAX_DAYS)
    db = _get_db()
    now = datetime.now(timezone.utc)
    start = now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days)
    events = db.get_events_in_range(
        start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    )
    local_tz = now.astimezone().tzinfo
    return {
        "now": now.astimezone().isoformat(),
        "timezone": str(local_tz) if local_tz else "",
        "days": days,
        "events": [encode_event(e) for e in events],
    }


@mcp.tool
async def get_event_json(event_id: int) -> dict:
    """Machine-readable variant of get_event. Returns None-valued fields
    when a value is absent rather than omitting them, so clients can treat
    the shape as stable.

    Args:
        event_id: The event rowid (as returned by get_today_json etc.).
    """
    db = _get_db()
    event = db.get_event(event_id)
    if not event:
        return {"id": event_id, "found": False}
    return {"found": True, **encode_event_detail(event)}


@mcp.tool
async def show_date(date: str) -> str:
    """Open Fantastical's mini calendar to a specific date.

    Args:
        date: Date in YYYY-MM-DD format.
    """
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return f"Invalid date format: {date}. Use YYYY-MM-DD."
    url = show_date_url(date)
    execute_url(url, background=False)
    return f"Opened Fantastical to {date}."


def main():
    """Main entry point for the Fantastical MCP server."""
    if TRANSPORT == "sse":
        mcp.run(transport="sse", host=HTTP_HOST, port=HTTP_PORT)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
