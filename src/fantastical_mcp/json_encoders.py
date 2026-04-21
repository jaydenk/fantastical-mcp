"""Convert internal event dicts into JSON-safe wire shapes.

The text formatters in ``formatters.py`` remain authoritative for the
existing text tools. These encoders are used by the JSON-variant tools
(``get_today_json`` etc.) so machine clients can consume structured data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def encode_event(event: dict) -> dict[str, Any]:
    """Return a JSON-safe summary of a single event.

    Keeps just the fields useful to a machine client — omits heavy blobs
    like full attendee lists (use ``encode_event_detail`` for that).
    """
    attendees = event.get("attendees") or []
    return {
        "id": event.get("rowid"),
        "title": event.get("title", ""),
        "calendar": event.get("calendar", ""),
        "start": _iso(event.get("start")),
        "end": _iso(event.get("end")),
        "all_day": bool(event.get("is_all_day")),
        "location": event.get("location") or None,
        "recurring": bool(event.get("recurring")),
        "attendees_count": len(attendees),
    }


def encode_event_detail(event: dict) -> dict[str, Any]:
    """Full-fat event dict for ``get_event_json`` callers."""
    base = encode_event(event)
    organizer = event.get("organizer") or None
    attendees = event.get("attendees") or []
    return {
        **base,
        "notes": event.get("notes") or None,
        "organizer": (
            {
                "displayName": organizer.get("displayName"),
                "emailAddress": organizer.get("emailAddress"),
            }
            if organizer
            else None
        ),
        "attendees": [
            {
                "displayName": att.get("displayName"),
                "emailAddress": att.get("emailAddress"),
            }
            for att in attendees
        ],
    }
