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
from .url_scheme import create_event_url, execute_url, show_date_url

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TRANSPORT = os.environ.get("FANTASTICAL_MCP_TRANSPORT", "stdio")
HTTP_HOST = os.environ.get("FANTASTICAL_MCP_HOST", "127.0.0.1")
HTTP_PORT = int(os.environ.get("FANTASTICAL_MCP_PORT", "8000"))

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

    if calendars:
        events = []
        for cal in calendars:
            events.extend(db.get_events_by_calendar(cal, days=1))
        events = [
            e for e in events
            if e.get("start") and e["start"].date() == local_start.date()
        ]
    else:
        events = db.get_events_in_range(start, end)

    return format_availability(events, date)


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
async def show_date(date: str) -> str:
    """Open Fantastical's mini calendar to a specific date.

    Args:
        date: Date in YYYY-MM-DD format.
    """
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
