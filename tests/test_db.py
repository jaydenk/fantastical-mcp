"""Tests for the database access layer — connection and calendar registry."""

import os
import plistlib
import sqlite3

import pytest

from fantastical_mcp.db import (
    DEFAULT_EXCLUDE_CALENDARS,
    FantasticalDB,
    find_database_path,
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
