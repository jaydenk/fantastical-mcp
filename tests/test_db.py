"""Tests for the database access layer — connection and calendar registry."""

import os
import plistlib
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from fantastical_mcp.db import (
    DEFAULT_EXCLUDE_CALENDARS,
    NSDATE_OFFSET,
    FantasticalDB,
    find_database_path,
    nsdate_to_datetime,
    resolve_uid,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_calendar_blob(title: str, identifier: str) -> bytes:
    """Build a minimal NSKeyedArchiver binary plist for a calendar entry.

    The blob mimics Fantastical's real FBCalendar serialisation format with
    ``$objects``, ``$top``, ``$archiver``, and ``$version`` keys.
    """
    plist = {
        "$version": 100000,
        "$archiver": "NSKeyedArchiver",
        "$top": {"root": plistlib.UID(1)},
        "$objects": [
            "$null",
            # [1] root dict — only the fields we care about
            {
                "title": plistlib.UID(2),
                "identifier": plistlib.UID(3),
            },
            # [2] title string
            title,
            # [3] identifier string
            identifier,
            # [4] class descriptor
            {
                "$classname": "FBCalendar",
                "$classes": ["FBCalendar", "FBMTLModel", "MTLModel", "NSObject"],
            },
        ],
    }
    return plistlib.dumps(plist, fmt=plistlib.FMT_BINARY)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SCHEMA_DATABASE2 = """
CREATE TABLE database2 (
    rowid   INTEGER PRIMARY KEY,
    collection CHAR NOT NULL,
    key     CHAR NOT NULL,
    data    BLOB,
    metadata BLOB
);
"""

_SCHEMA_SECONDARY_INDEX = """
CREATE TABLE secondaryIndex_index_calendarItems (
    rowid                       INTEGER PRIMARY KEY,
    syncStatus                  INTEGER,
    recurring                   INTEGER,
    calendarIdentifier          TEXT,
    hasEtag                     INTEGER,
    href                        TEXT,
    hasDownloadedAllAttachments INTEGER,
    hasUploadedAllAttachments   INTEGER,
    hasDownloadedAnyAttachments INTEGER,
    hasMovedToIdentifier        INTEGER,
    searchIndexModificationDate REAL,
    watchStableIdentifier       TEXT,
    hidden                      INTEGER,
    exchangeUID                 TEXT,
    isAllDayOrFloating          INTEGER,
    startDate                   REAL,
    recurrenceEndDate           REAL,
    invitationNeedsAction       INTEGER,
    hasDueDate                  INTEGER,
    dueDate                     REAL,
    completionDate              REAL,
    completed                   INTEGER,
    resolvedEventIdentifier     TEXT
);
"""

_SCHEMA_FTS = """
CREATE VIRTUAL TABLE fts_fts USING fts5(
    title, location, notes, URL, attendees, attachments,
    tokenize="unicode61 categories 'L* N* S* Co'"
);
"""


@pytest.fixture()
def test_db(tmp_path):
    """Create a temporary SQLite database with Fantastical's schema and seed data."""
    db_path = tmp_path / "Fantastical-test.fcdata"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    cur.executescript(_SCHEMA_DATABASE2)
    cur.executescript(_SCHEMA_SECONDARY_INDEX)
    cur.executescript(_SCHEMA_FTS)

    # Insert three calendars
    calendars = [
        ("abc123", "Work"),
        ("def456", "Personal"),
        ("CurrentWeather", "Weather"),
    ]
    for cal_id, cal_name in calendars:
        blob = _create_calendar_blob(cal_name, cal_id)
        cur.execute(
            "INSERT INTO database2 (collection, key, data) VALUES (?, ?, ?)",
            ("calendars", cal_id, blob),
        )

    # Insert some calendar-item rows so get_calendars() can count them
    for _ in range(5):
        cur.execute(
            "INSERT INTO secondaryIndex_index_calendarItems (calendarIdentifier) VALUES (?)",
            ("abc123",),
        )
    for _ in range(3):
        cur.execute(
            "INSERT INTO secondaryIndex_index_calendarItems (calendarIdentifier) VALUES (?)",
            ("def456",),
        )
    for _ in range(2):
        cur.execute(
            "INSERT INTO secondaryIndex_index_calendarItems (calendarIdentifier) VALUES (?)",
            ("CurrentWeather",),
        )

    conn.commit()
    conn.close()

    return db_path


# ---------------------------------------------------------------------------
# resolve_uid tests
# ---------------------------------------------------------------------------


class TestResolveUid:
    """Tests for the resolve_uid helper."""

    def test_plistlib_uid(self):
        objects = ["$null", "hello", "world"]
        assert resolve_uid(objects, plistlib.UID(1)) == "hello"

    def test_dict_with_cf_uid(self):
        objects = ["$null", "hello", "world"]
        assert resolve_uid(objects, {"CF$UID": 2}) == "world"

    def test_int_reference(self):
        objects = ["$null", "hello", "world"]
        assert resolve_uid(objects, 2) == "world"

    def test_null_index_returns_none(self):
        objects = ["$null", "hello"]
        assert resolve_uid(objects, plistlib.UID(0)) is None

    def test_null_int_returns_none(self):
        objects = ["$null", "hello"]
        assert resolve_uid(objects, 0) is None


# ---------------------------------------------------------------------------
# Calendar registry tests
# ---------------------------------------------------------------------------


class TestCalendarRegistry:
    """Tests for FantasticalDB calendar loading and lookup."""

    def test_loads_calendars(self, test_db):
        db = FantasticalDB(str(test_db))
        try:
            cals = db.get_calendars()
            names = {c["name"] for c in cals}
            assert "Work" in names
            assert "Personal" in names
        finally:
            db.close()

    def test_excludes_weather_by_default(self, test_db):
        db = FantasticalDB(str(test_db))
        try:
            cals = db.get_calendars()
            names = {c["name"] for c in cals}
            assert "Weather" not in names
        finally:
            db.close()

    def test_custom_exclusions(self, test_db):
        db = FantasticalDB(str(test_db), exclude_calendars={"Work"})
        try:
            cals = db.get_calendars()
            names = {c["name"] for c in cals}
            assert "Work" not in names
            # Weather is NOT excluded when custom set overrides defaults
            assert "Weather" in names
            assert "Personal" in names
        finally:
            db.close()

    def test_calendar_id_to_name(self, test_db):
        db = FantasticalDB(str(test_db))
        try:
            assert db.calendar_name("abc123") == "Work"
            assert db.calendar_name("def456") == "Personal"
            assert db.calendar_name("CurrentWeather") == "Weather"
            assert db.calendar_name("nonexistent") is None
        finally:
            db.close()

    def test_event_counts(self, test_db):
        db = FantasticalDB(str(test_db))
        try:
            cals = db.get_calendars()
            by_name = {c["name"]: c for c in cals}
            assert by_name["Work"]["event_count"] == 5
            assert by_name["Personal"]["event_count"] == 3
        finally:
            db.close()


# ---------------------------------------------------------------------------
# find_database_path tests
# ---------------------------------------------------------------------------


class TestFindDatabasePath:
    """Tests for auto-discovery of the Fantastical database file."""

    def test_env_var_override(self, tmp_path, monkeypatch):
        fake = tmp_path / "Fantastical-8.fcdata"
        fake.touch()
        monkeypatch.setenv("FANTASTICAL_DB_PATH", str(fake))
        assert find_database_path() == str(fake)

    def test_env_var_missing_file_raises(self, monkeypatch):
        monkeypatch.setenv("FANTASTICAL_DB_PATH", "/nonexistent/path.fcdata")
        with pytest.raises(FileNotFoundError):
            find_database_path()

    def test_no_env_no_file_raises(self, monkeypatch):
        monkeypatch.delenv("FANTASTICAL_DB_PATH", raising=False)
        # Patch glob to return nothing so we don't depend on the real DB
        import fantastical_mcp.db as db_mod

        monkeypatch.setattr(db_mod.glob, "glob", lambda _: [])
        with pytest.raises(FileNotFoundError):
            find_database_path()


# ---------------------------------------------------------------------------
# Environment-based exclusion tests
# ---------------------------------------------------------------------------


class TestExcludeCalendarsEnvVar:
    """Tests for FANTASTICAL_EXCLUDE_CALENDARS environment variable."""

    def test_env_var_exclusions(self, test_db, monkeypatch):
        monkeypatch.setenv("FANTASTICAL_EXCLUDE_CALENDARS", "Personal")
        db = FantasticalDB(str(test_db))
        try:
            cals = db.get_calendars()
            names = {c["name"] for c in cals}
            assert "Personal" not in names
            assert "Work" in names
            # env var replaces defaults, so Weather is back
            assert "Weather" in names
        finally:
            db.close()

    def test_explicit_param_takes_precedence(self, test_db, monkeypatch):
        monkeypatch.setenv("FANTASTICAL_EXCLUDE_CALENDARS", "Personal")
        db = FantasticalDB(str(test_db), exclude_calendars={"Work"})
        try:
            cals = db.get_calendars()
            names = {c["name"] for c in cals}
            # Explicit param wins over env var
            assert "Work" not in names
            assert "Personal" in names
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Event blob helpers
# ---------------------------------------------------------------------------


def _datetime_to_nsdate(dt: datetime) -> float:
    """Convert a Python datetime to an NSDate timestamp (seconds since 2001-01-01)."""
    return dt.timestamp() - NSDATE_OFFSET


def _create_event_blob(
    title: str = "Untitled",
    location: str = "",
    notes: str = "",
    calendar_id: str = "abc123",
    start: datetime | None = None,
    end: datetime | None = None,
    is_all_day: bool = False,
    attendees: list[dict[str, str]] | None = None,
    organizer: dict[str, str] | None = None,
    has_recurrence: bool = False,
    conference_type: int = 0,
    availability: int = 0,
) -> bytes:
    """Build a minimal FBEvent NSKeyedArchiver binary plist.

    The $objects array layout:
        [0]  "$null"
        [1]  root dict (FBEvent fields with UID refs)
        [2]  title string
        [3]  location string
        [4]  notes string
        [5]  calendarIdentifier string
        [6]  startDate dict  {NS.time: float}
        [7]  endDate dict    {NS.time: float}
        [8]  attendees array (NSArray wrapper) — may be empty
        [9]  organizer dict  (or "$null" placeholder string)
        [10] recurrenceRule  (or "$null" placeholder string)
        [11] $class descriptor for FBEvent
    """
    if start is None:
        start = datetime.now(tz=timezone.utc)
    if end is None:
        end = start + timedelta(hours=1)
    if attendees is None:
        attendees = []

    objects: list = [
        # [0] $null sentinel
        "$null",
    ]

    # --- Build attendee sub-objects and the NS.objects array of UIDs ---
    # We'll place attendee objects starting at index 12 onward.
    attendee_uids: list[plistlib.UID] = []
    attendee_objects: list[dict] = []
    base_idx = 12  # first attendee object index
    for i, att in enumerate(attendees):
        idx = base_idx + i * 3  # each attendee takes 3 slots: dict, displayName, email
        attendee_uids.append(plistlib.UID(idx))
        attendee_objects.append(
            {
                "displayName": plistlib.UID(idx + 1),
                "emailAddress": plistlib.UID(idx + 2),
            }
        )
        attendee_objects.append(att.get("displayName", ""))
        attendee_objects.append(att.get("emailAddress", ""))

    # Organizer handling: if provided, it goes right after attendees
    organizer_base = base_idx + len(attendees) * 3
    if organizer:
        organizer_uid = plistlib.UID(organizer_base)
        organizer_objects = [
            {
                "displayName": plistlib.UID(organizer_base + 1),
                "emailAddress": plistlib.UID(organizer_base + 2),
            },
            organizer.get("displayName", ""),
            organizer.get("emailAddress", ""),
        ]
    else:
        organizer_uid = plistlib.UID(0)  # points to $null
        organizer_objects = []

    # [1] root dict
    root = {
        "title": plistlib.UID(2),
        "location": plistlib.UID(3),
        "notes": plistlib.UID(4),
        "calendarIdentifier": plistlib.UID(5),
        "startDate": plistlib.UID(6),
        "endDate": plistlib.UID(7),
        "isAllDay": is_all_day,
        "attendees": plistlib.UID(8),
        "organizer": organizer_uid,
        "recurrenceRule": plistlib.UID(10) if has_recurrence else plistlib.UID(0),
        "conferenceType": conference_type,
        "availability": availability,
    }
    objects.append(root)  # [1]

    # [2] title
    objects.append(title)
    # [3] location
    objects.append(location)
    # [4] notes
    objects.append(notes)
    # [5] calendarIdentifier
    objects.append(calendar_id)

    # [6] startDate — nested dict with NS.time
    objects.append({"NS.time": _datetime_to_nsdate(start)})
    # [7] endDate
    objects.append({"NS.time": _datetime_to_nsdate(end)})

    # [8] attendees NS.objects array (UIDs pointing to attendee dicts)
    objects.append({"NS.objects": attendee_uids})

    # [9] organizer placeholder (or "$null" if no organizer — but we use UID(0) in root)
    objects.append("$null")  # placeholder at index 9

    # [10] recurrenceRule placeholder
    if has_recurrence:
        objects.append({"frequency": 1, "interval": 1})  # minimal recurrence rule
    else:
        objects.append("$null")  # placeholder

    # [11] class descriptor
    objects.append(
        {
            "$classname": "FBEvent",
            "$classes": ["FBEvent", "FBMTLModel", "MTLModel", "NSObject"],
        }
    )

    # [12+] attendee objects
    objects.extend(attendee_objects)

    # organizer objects
    objects.extend(organizer_objects)

    plist = {
        "$version": 100000,
        "$archiver": "NSKeyedArchiver",
        "$top": {"root": plistlib.UID(1)},
        "$objects": objects,
    }
    return plistlib.dumps(plist, fmt=plistlib.FMT_BINARY)


def _insert_event(
    conn: sqlite3.Connection,
    rowid: int,
    cal_id: str,
    blob: bytes,
    start: datetime,
    end: datetime,
    title: str = "",
    location: str = "",
    notes: str = "",
    hidden: int | None = None,
    is_all_day: int = 0,
) -> None:
    """Insert an event into database2, secondaryIndex, and fts_fts."""
    cur = conn.cursor()

    # database2 row
    collection = f"calendarItems-{cal_id}"
    cur.execute(
        "INSERT INTO database2 (rowid, collection, key, data) VALUES (?, ?, ?, ?)",
        (rowid, collection, f"event-{rowid}", blob),
    )

    # secondaryIndex row
    ns_start = _datetime_to_nsdate(start)
    ns_end = _datetime_to_nsdate(end)
    cur.execute(
        "INSERT INTO secondaryIndex_index_calendarItems "
        "(rowid, calendarIdentifier, startDate, recurrenceEndDate, hidden, isAllDayOrFloating) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (rowid, cal_id, ns_start, ns_end, hidden, is_all_day),
    )

    # fts_fts row (uses implicit rowid)
    cur.execute(
        "INSERT INTO fts_fts (rowid, title, location, notes, URL, attendees, attachments) "
        "VALUES (?, ?, ?, ?, '', '', '')",
        (rowid, title, location, notes),
    )

    conn.commit()


# ---------------------------------------------------------------------------
# populated_db fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def populated_db(test_db):
    """Add two concrete events to the test database.

    Events:
    - rowid 100: "Team Standup" today 09:00-10:00 UTC, Work calendar (abc123)
    - rowid 101: "Lunch with Sara" tomorrow 14:00-15:00 UTC, Personal calendar (def456)
    """
    conn = sqlite3.connect(str(test_db))

    now = datetime.now(tz=timezone.utc)
    today_9 = now.replace(hour=9, minute=0, second=0, microsecond=0)
    today_10 = now.replace(hour=10, minute=0, second=0, microsecond=0)
    tomorrow_14 = (now + timedelta(days=1)).replace(
        hour=14, minute=0, second=0, microsecond=0
    )
    tomorrow_15 = (now + timedelta(days=1)).replace(
        hour=15, minute=0, second=0, microsecond=0
    )

    blob1 = _create_event_blob(
        title="Team Standup",
        location="Meeting Room A",
        notes="",
        calendar_id="abc123",
        start=today_9,
        end=today_10,
    )
    _insert_event(
        conn,
        rowid=100,
        cal_id="abc123",
        blob=blob1,
        start=today_9,
        end=today_10,
        title="Team Standup",
        location="Meeting Room A",
    )

    blob2 = _create_event_blob(
        title="Lunch with Sara",
        location="The Crafers Hotel",
        notes="Book table",
        calendar_id="def456",
        start=tomorrow_14,
        end=tomorrow_15,
    )
    _insert_event(
        conn,
        rowid=101,
        cal_id="def456",
        blob=blob2,
        start=tomorrow_14,
        end=tomorrow_15,
        title="Lunch with Sara",
        location="The Crafers Hotel",
        notes="Book table",
    )

    conn.close()
    return test_db


# ---------------------------------------------------------------------------
# NSDate conversion tests
# ---------------------------------------------------------------------------


class TestNSDateConversion:
    """Tests for nsdate_to_datetime helper."""

    def test_known_date_converts_correctly(self):
        """2001-01-01 00:00:00 UTC is NSDate epoch (0.0)."""
        result = nsdate_to_datetime(0.0)
        expected = datetime(2001, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert result == expected

    def test_roundtrip(self):
        """Converting to NSDate and back should yield the original datetime."""
        original = datetime(2025, 6, 15, 12, 30, 0, tzinfo=timezone.utc)
        ns_val = _datetime_to_nsdate(original)
        result = nsdate_to_datetime(ns_val)
        assert abs((result - original).total_seconds()) < 1


# ---------------------------------------------------------------------------
# Event decoding tests
# ---------------------------------------------------------------------------


class TestEventDecoding:
    """Tests for FantasticalDB.decode_event and get_events_in_range."""

    def test_decode_event_blob(self, populated_db):
        """Both inserted events should be decodable."""
        db = FantasticalDB(str(populated_db))
        try:
            conn = sqlite3.connect(str(populated_db))
            cur = conn.cursor()
            cur.execute("SELECT rowid, data FROM database2 WHERE collection LIKE 'calendarItems-%'")
            rows = cur.fetchall()
            conn.close()

            decoded = []
            for row in rows:
                event = db.decode_event(row[1], row[0])
                if event is not None:
                    decoded.append(event)
            assert len(decoded) == 2
        finally:
            db.close()

    def test_event_has_required_fields(self, populated_db):
        """Decoded events must contain all expected keys."""
        db = FantasticalDB(str(populated_db))
        try:
            conn = sqlite3.connect(str(populated_db))
            cur = conn.cursor()
            cur.execute(
                "SELECT rowid, data FROM database2 WHERE collection LIKE 'calendarItems-%' LIMIT 1"
            )
            row = cur.fetchone()
            conn.close()

            event = db.decode_event(row[1], row[0])
            assert event is not None
            required_keys = {
                "rowid",
                "title",
                "location",
                "notes",
                "start",
                "end",
                "calendar_id",
                "calendar",
                "is_all_day",
                "recurring",
                "attendees",
                "organizer",
                "conference_type",
            }
            assert required_keys.issubset(event.keys())
        finally:
            db.close()

    def test_get_events_filters_by_date(self, populated_db):
        """Querying today's range should return only today's event."""
        db = FantasticalDB(str(populated_db))
        try:
            now = datetime.now(tz=timezone.utc)
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            events = db.get_events_in_range(day_start, day_end)
            assert len(events) == 1
            assert events[0]["title"] == "Team Standup"
        finally:
            db.close()

    def test_get_events_returns_both(self, populated_db):
        """Querying a two-day range should return both events."""
        db = FantasticalDB(str(populated_db))
        try:
            now = datetime.now(tz=timezone.utc)
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=2)
            events = db.get_events_in_range(day_start, day_end)
            assert len(events) == 2
        finally:
            db.close()

    def test_excludes_hidden_calendars(self, populated_db):
        """Events from hidden calendars (e.g. Weather) should be excluded."""
        # Add a weather event
        conn = sqlite3.connect(str(populated_db))
        now = datetime.now(tz=timezone.utc)
        today_8 = now.replace(hour=8, minute=0, second=0, microsecond=0)
        today_9 = now.replace(hour=9, minute=0, second=0, microsecond=0)

        blob = _create_event_blob(
            title="Sunny 25°C",
            location="Adelaide",
            calendar_id="CurrentWeather",
            start=today_8,
            end=today_9,
        )
        _insert_event(
            conn,
            rowid=200,
            cal_id="CurrentWeather",
            blob=blob,
            start=today_8,
            end=today_9,
            title="Sunny 25°C",
            location="Adelaide",
        )
        conn.close()

        db = FantasticalDB(str(populated_db))
        try:
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            events = db.get_events_in_range(day_start, day_end)
            titles = [e["title"] for e in events]
            assert "Sunny 25°C" not in titles
            # Team Standup should still be there
            assert "Team Standup" in titles
        finally:
            db.close()

    def test_decode_corrupt_blob_returns_none(self, test_db):
        """Corrupt blob data should return None, not raise."""
        db = FantasticalDB(str(test_db))
        try:
            result = db.decode_event(b"not a plist", 999)
            assert result is None
        finally:
            db.close()


# ---------------------------------------------------------------------------
# FTS search tests
# ---------------------------------------------------------------------------


class TestSearchEvents:
    def test_search_by_title(self, populated_db):
        db = FantasticalDB(str(populated_db))
        try:
            results = db.search_events("Standup")
            assert len(results) == 1
            assert results[0]["title"] == "Team Standup"
        finally:
            db.close()

    def test_search_by_location(self, populated_db):
        db = FantasticalDB(str(populated_db))
        try:
            results = db.search_events("Crafers")
            assert len(results) == 1
            assert results[0]["title"] == "Lunch with Sara"
        finally:
            db.close()

    def test_search_no_results(self, populated_db):
        db = FantasticalDB(str(populated_db))
        try:
            results = db.search_events("nonexistent")
            assert len(results) == 0
        finally:
            db.close()

    def test_search_respects_limit(self, populated_db):
        db = FantasticalDB(str(populated_db))
        try:
            # Use a broad prefix query — FTS5 does not accept bare '*'.
            results = db.search_events("T*", limit=1)
            assert len(results) <= 1
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Calendar filter tests
# ---------------------------------------------------------------------------


class TestGetEventsByCalendar:
    def test_filter_by_calendar_name(self, populated_db):
        db = FantasticalDB(str(populated_db))
        try:
            events = db.get_events_by_calendar("Work")
            assert all(e["calendar"] == "Work" for e in events)
            assert any(e["title"] == "Team Standup" for e in events)
        finally:
            db.close()

    def test_filter_by_calendar_no_results(self, populated_db):
        db = FantasticalDB(str(populated_db))
        try:
            events = db.get_events_by_calendar("Nonexistent Calendar")
            assert len(events) == 0
        finally:
            db.close()

    def test_filter_with_date_range(self, populated_db):
        db = FantasticalDB(str(populated_db))
        try:
            events = db.get_events_by_calendar("Personal", days=30)
            assert any(e["title"] == "Lunch with Sara" for e in events)
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Single event lookup tests
# ---------------------------------------------------------------------------


class TestGetEventById:
    def test_get_existing_event(self, populated_db):
        db = FantasticalDB(str(populated_db))
        try:
            events = db.get_events_in_range(
                datetime.now(timezone.utc) - timedelta(hours=1),
                datetime.now(timezone.utc) + timedelta(days=2),
            )
            assert len(events) > 0
            event = db.get_event(events[0]["rowid"])
            assert event is not None
            assert event["title"] == events[0]["title"]
        finally:
            db.close()

    def test_get_nonexistent_event(self, populated_db):
        db = FantasticalDB(str(populated_db))
        try:
            event = db.get_event(99999)
            assert event is None
        finally:
            db.close()
