"""Output formatters for calendar events and search results.

All display text uses Australian English (e.g. "Organiser" not "Organizer").
Times are converted from UTC to the system's local timezone for display.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _local_dt(dt: datetime) -> datetime:
    """Convert a UTC datetime to the system's local timezone."""
    return dt.astimezone()


def _format_time(dt: datetime) -> str:
    """Format a datetime as HH:MM in local time."""
    return _local_dt(dt).strftime("%H:%M")


def _format_date_heading(dt: datetime) -> str:
    """Format a datetime as 'Monday 30 March 2026' in local time."""
    return _local_dt(dt).strftime("%A %-d %B %Y")


def _truncate_location(location: str, max_len: int = 60) -> str:
    """Truncate location to *max_len* chars, first line only."""
    first_line = location.split("\n")[0]
    if len(first_line) <= max_len:
        return first_line
    return first_line[: max_len - 1] + "…"


def _format_event_line(event: dict) -> str:
    """Format a single event as one display line.

    Timed:   ``  09:00 – 10:00  Team Standup @ Meeting Room A (id:42)``
    All-day: ``  All day  Labour Day (id:86125)``
    """
    parts: list[str] = ["  "]

    if event["is_all_day"]:
        parts.append("All day  ")
    else:
        parts.append(f"{_format_time(event['start'])} – {_format_time(event['end'])}  ")

    parts.append(event["title"])

    location = event.get("location", "")
    if location:
        parts.append(f" @ {_truncate_location(location)}")

    if event.get("recurring"):
        parts.append(" (recurring)")

    parts.append(f" (id:{event['rowid']})")

    return "".join(parts)


def _format_duration(minutes: int) -> str:
    """Human-readable duration from minutes, e.g. '2h 30min'."""
    if minutes < 60:
        return f"{minutes}min"
    hours, mins = divmod(minutes, 60)
    if mins == 0:
        return f"{hours}h"
    return f"{hours}h {mins}min"


def _local_date(dt: datetime) -> str:
    """Return the local date portion as YYYY-MM-DD for grouping."""
    return _local_dt(dt).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Public formatters
# ---------------------------------------------------------------------------


def format_events_by_date(events: list[dict]) -> str:
    """Group events by date, show date headings with event lines beneath.

    Returns ``"No events found."`` if the list is empty.
    """
    if not events:
        return "No events found."

    # Group by local date.
    grouped: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        key = _local_date(ev["start"])
        grouped[key].append(ev)

    lines: list[str] = []
    for date_key in sorted(grouped):
        day_events = grouped[date_key]
        heading = _format_date_heading(day_events[0]["start"])
        lines.append(heading)
        for ev in day_events:
            lines.append(_format_event_line(ev))
        lines.append("")  # blank line between date groups

    return "\n".join(lines).rstrip()


def format_events_by_calendar(events: list[dict]) -> str:
    """Group events by calendar name, show calendar headings with event lines.

    Returns ``"No events found."`` if the list is empty.
    """
    if not events:
        return "No events found."

    grouped: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        grouped[ev["calendar"]].append(ev)

    lines: list[str] = []
    for cal_name in sorted(grouped):
        lines.append(cal_name)
        for ev in grouped[cal_name]:
            lines.append(_format_event_line(ev))
        lines.append("")

    return "\n".join(lines).rstrip()


def format_event_detail(event: dict) -> str:
    """Full event detail block.

    Includes title, calendar, date, time range, location, organiser,
    attendees, notes, recurring flag, and ID.
    """
    lines: list[str] = []
    lines.append(event["title"])
    lines.append(f"Calendar: {event['calendar']}")

    if event["start"]:
        lines.append(f"Date: {_format_date_heading(event['start'])}")

    if event["is_all_day"]:
        lines.append("Time: All day")
    elif event["start"] and event["end"]:
        lines.append(f"Time: {_format_time(event['start'])} – {_format_time(event['end'])}")

    location = event.get("location", "")
    if location:
        lines.append(f"Location: {location}")

    organizer = event.get("organizer")
    if organizer:
        name = organizer.get("displayName") or ""
        email = organizer.get("emailAddress") or ""
        if name and email:
            lines.append(f"Organiser: {name} <{email}>")
        elif name:
            lines.append(f"Organiser: {name}")
        elif email:
            lines.append(f"Organiser: {email}")

    attendees = event.get("attendees", [])
    if attendees:
        lines.append("Attendees:")
        for att in attendees:
            name = att.get("displayName") or ""
            email = att.get("emailAddress") or ""
            if name and email:
                lines.append(f"  - {name} <{email}>")
            elif name:
                lines.append(f"  - {name}")
            elif email:
                lines.append(f"  - {email}")

    notes = event.get("notes", "")
    if notes:
        lines.append(f"Notes: {notes}")

    if event.get("recurring"):
        lines.append("Recurring: Yes")

    lines.append(f"ID: {event['rowid']} (id:{event['rowid']})")

    return "\n".join(lines)


def format_calendars(calendars: list[dict]) -> str:
    """List calendars with name and event count.

    Returns ``"No calendars found."`` if the list is empty.
    """
    if not calendars:
        return "No calendars found."

    lines: list[str] = []
    for cal in calendars:
        lines.append(f"{cal['name']} ({cal['event_count']} events)")

    return "\n".join(lines)


def format_availability(events: list[dict], date_str: str) -> str:
    """Show busy blocks and free gaps for a given date.

    Timed events are listed as ``Busy:`` lines. Free gaps between 08:00 and
    18:00 local time are calculated and shown as ``Free:`` lines with
    durations. All-day events are listed separately at the end.

    Returns a section with ``"Fully available"`` if no timed events exist
    (all-day events are still listed if present).
    """
    all_day: list[dict] = []
    timed: list[dict] = []

    for ev in events:
        if ev["is_all_day"]:
            all_day.append(ev)
        else:
            timed.append(ev)

    # Sort timed events by start time.
    timed.sort(key=lambda e: e["start"])

    lines: list[str] = []
    lines.append(f"Availability for {date_str}")
    lines.append("")

    if not timed:
        lines.append("Fully available (08:00 – 18:00)")
    else:
        # Build busy/free blocks between 08:00 and 18:00 local time.
        # Parse the date_str to anchor our window.
        # Use the first event's timezone info as reference.
        ref_local = _local_dt(timed[0]["start"])
        local_tz = ref_local.tzinfo

        year, month, day = (int(p) for p in date_str.split("-"))
        window_start = datetime(year, month, day, 8, 0, 0, tzinfo=local_tz)
        window_end = datetime(year, month, day, 18, 0, 0, tzinfo=local_tz)

        # Collect busy intervals (clipped to window).
        busy_intervals: list[tuple[datetime, datetime, dict]] = []
        for ev in timed:
            ev_start_local = _local_dt(ev["start"])
            ev_end_local = _local_dt(ev["end"])
            clip_start = max(ev_start_local, window_start)
            clip_end = min(ev_end_local, window_end)
            if clip_start < clip_end:
                busy_intervals.append((clip_start, clip_end, ev))

        busy_intervals.sort(key=lambda x: x[0])

        # Interleave free and busy blocks.
        cursor = window_start
        for b_start, b_end, ev in busy_intervals:
            if b_start > cursor:
                gap_mins = int((b_start - cursor).total_seconds() / 60)
                lines.append(
                    f"Free: {cursor.strftime('%H:%M')} – {b_start.strftime('%H:%M')} "
                    f"({_format_duration(gap_mins)})"
                )
            lines.append(
                f"Busy: {b_start.strftime('%H:%M')} – {b_end.strftime('%H:%M')}  "
                f"{ev['title']} (id:{ev['rowid']})"
            )
            cursor = max(cursor, b_end)

        if cursor < window_end:
            gap_mins = int((window_end - cursor).total_seconds() / 60)
            lines.append(
                f"Free: {cursor.strftime('%H:%M')} – {window_end.strftime('%H:%M')} "
                f"({_format_duration(gap_mins)})"
            )

    # All-day events section.
    if all_day:
        lines.append("")
        lines.append("All-day events:")
        for ev in all_day:
            lines.append(f"  {ev['title']} (id:{ev['rowid']})")

    return "\n".join(lines)
