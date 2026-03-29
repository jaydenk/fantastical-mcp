"""Tests for plain-text output formatters."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fantastical_mcp.formatters import (
    format_availability,
    format_calendars,
    format_event_detail,
    format_events_by_calendar,
    format_events_by_date,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Determine the local timezone offset so that test times are always expressed
# as UTC instants that correspond to predictable local-clock values.  This
# avoids failures when the machine's timezone differs from the author's
# expectations.
_LOCAL_TZ = datetime.now().astimezone().tzinfo


def _local_to_utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """Create a UTC datetime from local-clock year/month/day/hour/minute."""
    local = datetime(year, month, day, hour, minute, 0, tzinfo=_LOCAL_TZ)
    return local.astimezone(timezone.utc)


def _make_event(
    rowid: int = 1,
    title: str = "Test Event",
    location: str | None = None,
    notes: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    calendar: str = "Work",
    calendar_id: str = "abc123",
    is_all_day: bool = False,
    recurring: bool = False,
    attendees: list[dict[str, str]] | None = None,
    organizer: dict[str, str | None] | None = None,
    conference_type: int = 0,
) -> dict:
    """Build an event dict with sensible defaults matching db.py output."""
    if start is None:
        start = _local_to_utc(2026, 3, 30, 9, 0)
    if end is None:
        end = start + timedelta(hours=1)
    if attendees is None:
        attendees = []

    return {
        "rowid": rowid,
        "title": title,
        "location": location or "",
        "notes": notes or "",
        "start": start,
        "end": end,
        "calendar": calendar,
        "calendar_id": calendar_id,
        "is_all_day": is_all_day,
        "recurring": recurring,
        "attendees": attendees,
        "organizer": organizer,
        "conference_type": conference_type,
    }


# ---------------------------------------------------------------------------
# TestFormatEventsByDate
# ---------------------------------------------------------------------------


class TestFormatEventsByDate:
    """Tests for format_events_by_date."""

    def test_empty_list(self):
        assert format_events_by_date([]) == "No events found."

    def test_groups_by_date(self):
        """Events on different local dates get separate date headings."""
        monday = _local_to_utc(2026, 3, 30, 9, 0)
        tuesday = _local_to_utc(2026, 3, 31, 14, 0)

        events = [
            _make_event(rowid=1, title="Morning Meeting", start=monday, end=monday + timedelta(hours=1)),
            _make_event(rowid=2, title="Afternoon Call", start=tuesday, end=tuesday + timedelta(hours=1)),
        ]
        result = format_events_by_date(events)

        assert "Monday 30 March 2026" in result
        assert "Tuesday 31 March 2026" in result
        assert "Morning Meeting" in result
        assert "Afternoon Call" in result

    def test_includes_event_ids(self):
        event = _make_event(rowid=42, title="Team Standup")
        result = format_events_by_date([event])
        assert "(id:42)" in result

    def test_shows_location(self):
        event = _make_event(rowid=1, title="Standup", location="Meeting Room A")
        result = format_events_by_date([event])
        assert "Meeting Room A" in result

    def test_shows_time_range(self):
        start = _local_to_utc(2026, 3, 30, 9, 0)
        end = _local_to_utc(2026, 3, 30, 10, 0)
        event = _make_event(rowid=1, start=start, end=end)
        result = format_events_by_date([event])
        # Should display "09:00 – 10:00" in local time
        assert "09:00 – 10:00" in result

    def test_all_day_event(self):
        event = _make_event(
            rowid=86125,
            title="Labour Day",
            is_all_day=True,
        )
        result = format_events_by_date([event])
        assert "All day" in result
        assert "Labour Day" in result
        assert "(id:86125)" in result

    def test_recurring_marker(self):
        event = _make_event(rowid=500, title="Support Officer Forum", recurring=True)
        result = format_events_by_date([event])
        assert "(recurring)" in result

    def test_multiple_events_same_date(self):
        start1 = _local_to_utc(2026, 3, 30, 9, 0)
        start2 = _local_to_utc(2026, 3, 30, 14, 0)
        events = [
            _make_event(rowid=1, title="Morning", start=start1),
            _make_event(rowid=2, title="Afternoon", start=start2),
        ]
        result = format_events_by_date(events)
        # Only one date heading
        assert result.count("Monday 30 March 2026") == 1
        assert "Morning" in result
        assert "Afternoon" in result


# ---------------------------------------------------------------------------
# TestFormatEventsByCalendar
# ---------------------------------------------------------------------------


class TestFormatEventsByCalendar:
    """Tests for format_events_by_calendar."""

    def test_empty_list(self):
        assert format_events_by_calendar([]) == "No events found."

    def test_groups_by_calendar(self):
        events = [
            _make_event(rowid=1, title="Standup", calendar="Work"),
            _make_event(rowid=2, title="Dinner", calendar="Personal"),
        ]
        result = format_events_by_calendar(events)
        assert "Work" in result
        assert "Personal" in result
        assert "Standup" in result
        assert "Dinner" in result

    def test_includes_time_and_title(self):
        start = _local_to_utc(2026, 3, 30, 9, 0)
        event = _make_event(rowid=1, title="Review", start=start, end=start + timedelta(hours=1))
        result = format_events_by_calendar([event])
        assert "Review" in result
        assert "(id:1)" in result

    def test_multiple_events_same_calendar(self):
        events = [
            _make_event(rowid=1, title="Morning Sync", calendar="Work"),
            _make_event(rowid=2, title="1:1 with Manager", calendar="Work"),
        ]
        result = format_events_by_calendar(events)
        # Only one calendar heading
        assert result.count("Work") == 1
        assert "Morning Sync" in result
        assert "1:1 with Manager" in result


# ---------------------------------------------------------------------------
# TestFormatEventDetail
# ---------------------------------------------------------------------------


class TestFormatEventDetail:
    """Tests for format_event_detail."""

    def test_full_event(self):
        event = _make_event(
            rowid=42,
            title="Team Standup",
            location="Meeting Room A",
            notes="Bring laptop",
            calendar="Work",
            recurring=True,
            attendees=[
                {"displayName": "Alice Smith", "emailAddress": "alice@example.com"},
                {"displayName": "Bob Jones", "emailAddress": "bob@example.com"},
            ],
            organizer={"displayName": "Alice Smith", "emailAddress": "alice@example.com"},
        )
        result = format_event_detail(event)

        assert "Team Standup" in result
        assert "Meeting Room A" in result
        assert "Bring laptop" in result
        assert "Work" in result
        assert "Alice Smith" in result
        assert "Bob Jones" in result
        # Australian English
        assert "Organiser" in result
        assert "id:42" in result
        assert "Recurring: Yes" in result

    def test_minimal_event(self):
        """Event with only required fields should not crash."""
        event = _make_event(
            rowid=1,
            title="Quick Chat",
            location="",
            notes="",
            attendees=[],
            organizer=None,
            recurring=False,
        )
        result = format_event_detail(event)
        assert "Quick Chat" in result
        assert "id:1" in result

    def test_attendees_listed(self):
        event = _make_event(
            rowid=1,
            attendees=[
                {"displayName": "Charlie", "emailAddress": "charlie@example.com"},
            ],
        )
        result = format_event_detail(event)
        assert "Charlie" in result
        assert "charlie@example.com" in result

    def test_shows_calendar_name(self):
        event = _make_event(rowid=1, calendar="Personal")
        result = format_event_detail(event)
        assert "Personal" in result

    def test_time_range_displayed(self):
        start = _local_to_utc(2026, 3, 30, 13, 30)
        end = _local_to_utc(2026, 3, 30, 14, 30)
        event = _make_event(rowid=1, start=start, end=end)
        result = format_event_detail(event)
        assert "13:30 – 14:30" in result


# ---------------------------------------------------------------------------
# TestFormatCalendars
# ---------------------------------------------------------------------------


class TestFormatCalendars:
    """Tests for format_calendars."""

    def test_empty_list(self):
        assert format_calendars([]) == "No calendars found."

    def test_lists_calendars_with_counts(self):
        calendars = [
            {"id": "abc", "name": "Work", "event_count": 42},
            {"id": "def", "name": "Personal", "event_count": 7},
        ]
        result = format_calendars(calendars)
        assert "Work" in result
        assert "42" in result
        assert "Personal" in result
        assert "7" in result

    def test_single_calendar(self):
        calendars = [{"id": "abc", "name": "Holidays", "event_count": 12}]
        result = format_calendars(calendars)
        assert "Holidays" in result
        assert "12" in result


# ---------------------------------------------------------------------------
# TestFormatAvailability
# ---------------------------------------------------------------------------


class TestFormatAvailability:
    """Tests for format_availability."""

    def test_no_timed_events(self):
        """No timed events should show fully available."""
        result = format_availability([], "2026-03-30")
        assert "Fully available" in result

    def test_shows_busy_and_free(self):
        """A single mid-morning event should produce busy + surrounding free blocks."""
        # 10:30 – 11:30 local time on 2026-03-30
        event = _make_event(
            rowid=1,
            title="Meeting",
            start=_local_to_utc(2026, 3, 30, 10, 30),
            end=_local_to_utc(2026, 3, 30, 11, 30),
            is_all_day=False,
        )
        result = format_availability([event], "2026-03-30")
        assert "Busy:" in result
        assert "Free:" in result
        assert "Meeting" in result

    def test_all_day_events_listed_separately(self):
        event = _make_event(
            rowid=1,
            title="Labour Day",
            is_all_day=True,
        )
        result = format_availability([event], "2026-03-30")
        assert "Labour Day" in result
        # All-day events don't create busy blocks, so should still be "fully available"
        assert "Fully available" in result

    def test_free_slot_durations(self):
        """Free slots should include a duration."""
        event = _make_event(
            rowid=1,
            title="Standup",
            start=_local_to_utc(2026, 3, 30, 9, 0),
            end=_local_to_utc(2026, 3, 30, 10, 0),
            is_all_day=False,
        )
        result = format_availability([event], "2026-03-30")
        # Free gap before (08:00 – 09:00 = 1h), and after (10:00 – 18:00 = 8h)
        assert "1h" in result
        assert "8h" in result

    def test_multiple_events_multiple_gaps(self):
        """Two events with a gap between should produce two busy and multiple free blocks."""
        events = [
            _make_event(
                rowid=1,
                title="Morning",
                start=_local_to_utc(2026, 3, 30, 9, 0),
                end=_local_to_utc(2026, 3, 30, 10, 0),
                is_all_day=False,
            ),
            _make_event(
                rowid=2,
                title="Afternoon",
                start=_local_to_utc(2026, 3, 30, 14, 0),
                end=_local_to_utc(2026, 3, 30, 15, 0),
                is_all_day=False,
            ),
        ]
        result = format_availability(events, "2026-03-30")
        assert result.count("Busy:") == 2
        # Free slots: before first (08:00-09:00), between (10:00-14:00), after (15:00-18:00)
        assert result.count("Free:") == 3

    def test_event_outside_window_excluded(self):
        """An event entirely outside 08:00-18:00 should not create a busy block."""
        event = _make_event(
            rowid=1,
            title="Late Night",
            start=_local_to_utc(2026, 3, 30, 20, 0),
            end=_local_to_utc(2026, 3, 30, 21, 0),
            is_all_day=False,
        )
        result = format_availability([event], "2026-03-30")
        # No busy blocks since the event is outside the window
        assert "Busy:" not in result
        assert "Free: 08:00 – 18:00" in result
