"""Tests for the JSON encoder helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fantastical_mcp.json_encoders import encode_event, encode_event_detail


_LOCAL_TZ = datetime.now().astimezone().tzinfo


def _make_event(**overrides):
    start = datetime(2026, 3, 30, 9, 0, tzinfo=timezone.utc)
    base = {
        "rowid": 42,
        "title": "Team Standup",
        "location": "Meeting Room A",
        "notes": "Bring laptop",
        "start": start,
        "end": start + timedelta(hours=1),
        "calendar": "Work",
        "calendar_id": "abc123",
        "is_all_day": False,
        "recurring": False,
        "attendees": [],
        "organizer": None,
    }
    base.update(overrides)
    return base


class TestEncodeEvent:
    def test_basic_timed_event(self):
        ev = _make_event()
        out = encode_event(ev)
        assert out["id"] == 42
        assert out["title"] == "Team Standup"
        assert out["calendar"] == "Work"
        assert out["location"] == "Meeting Room A"
        assert out["all_day"] is False
        assert out["recurring"] is False
        assert out["attendees_count"] == 0
        assert out["start"].startswith("2026-03-30T09:00:00")
        assert out["end"].startswith("2026-03-30T10:00:00")

    def test_empty_location_becomes_null(self):
        out = encode_event(_make_event(location=""))
        assert out["location"] is None

    def test_missing_location_is_null(self):
        ev = _make_event()
        del ev["location"]
        out = encode_event(ev)
        assert out["location"] is None

    def test_all_day_and_recurring_flags(self):
        out = encode_event(_make_event(is_all_day=True, recurring=True))
        assert out["all_day"] is True
        assert out["recurring"] is True

    def test_attendees_count_only(self):
        attendees = [
            {"displayName": "Alice", "emailAddress": "alice@example.com"},
            {"displayName": "Bob", "emailAddress": "bob@example.com"},
        ]
        out = encode_event(_make_event(attendees=attendees))
        assert out["attendees_count"] == 2
        # summary shape doesn't expose the full list
        assert "attendees" not in out

    def test_null_times(self):
        out = encode_event(_make_event(start=None, end=None))
        assert out["start"] is None
        assert out["end"] is None


class TestEncodeEventDetail:
    def test_includes_notes_organiser_attendees(self):
        attendees = [{"displayName": "Alice", "emailAddress": "alice@example.com"}]
        ev = _make_event(
            attendees=attendees,
            organizer={"displayName": "Bob", "emailAddress": "bob@example.com"},
        )
        out = encode_event_detail(ev)
        assert out["notes"] == "Bring laptop"
        assert out["organizer"] == {
            "displayName": "Bob",
            "emailAddress": "bob@example.com",
        }
        assert out["attendees"] == attendees
        # inherits summary fields
        assert out["id"] == 42
        assert out["attendees_count"] == 1

    def test_empty_notes_becomes_null(self):
        out = encode_event_detail(_make_event(notes=""))
        assert out["notes"] is None

    def test_missing_organizer_is_null(self):
        out = encode_event_detail(_make_event(organizer=None))
        assert out["organizer"] is None
