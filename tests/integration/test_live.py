"""Integration tests — require Fantastical installed with calendar data."""

import pytest
from fantastical_mcp.db import FantasticalDB, find_database_path


pytestmark = pytest.mark.integration


class TestLiveDatabase:
    @pytest.fixture(autouse=True)
    def setup_db(self):
        try:
            self.db = FantasticalDB(find_database_path())
        except FileNotFoundError:
            pytest.skip("Fantastical database not found")

    def test_discovers_database(self):
        assert self.db is not None

    def test_loads_calendars(self):
        calendars = self.db.get_calendars()
        assert len(calendars) > 0

    def test_get_today_returns_events(self):
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        events = self.db.get_events_in_range(start, end)
        # May be empty on weekends, just check it doesn't crash
        assert isinstance(events, list)

    def test_search_returns_results(self):
        results = self.db.search_events("Meeting")
        assert isinstance(results, list)
        # Don't assert specific count — depends on user's calendar

    def test_calendar_names_are_readable(self):
        calendars = self.db.get_calendars()
        for cal in calendars:
            assert isinstance(cal["name"], str)
            assert len(cal["name"]) > 0

    def test_event_detail_returns_all_fields(self):
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        events = self.db.get_events_in_range(
            now - timedelta(days=7), now + timedelta(days=7)
        )
        if not events:
            pytest.skip("No events in the last/next 7 days")
        event = self.db.get_event(events[0]["rowid"])
        assert event is not None
        assert "title" in event
        assert "start" in event
        assert "calendar" in event

    def test_get_events_by_calendar_works(self):
        calendars = self.db.get_calendars()
        if not calendars:
            pytest.skip("No calendars found")
        events = self.db.get_events_by_calendar(calendars[0]["name"], days=30)
        assert isinstance(events, list)
