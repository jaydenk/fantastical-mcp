"""Database access layer for Fantastical's local SQLite store."""

from __future__ import annotations

import glob
import logging
import os
import plistlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Seconds between the Unix epoch (1970-01-01) and the NSDate reference date
# (2001-01-01).  Used to convert NSDate timestamps to Unix timestamps.
NSDATE_OFFSET = 978307200

# Calendar names that are excluded from query results by default.  These are
# Fantastical system calendars that clutter normal usage.
DEFAULT_EXCLUDE_CALENDARS: set[str] = {
    "Weather",
    "Openings",
    "RSVP Invitations",
    "Proposals",
    "Notifications",
}

# Calendars excluded from recurring event listings by default.
# Birthdays and Anniversaries dominate recurring results without adding value.
DEFAULT_RECURRING_EXCLUDE_CALENDARS: set[str] = {
    "Birthdays",
    "Anniversaries",
}

_DB_GLOB = os.path.expanduser(
    "~/Library/Group Containers/"
    "85C27NK92C.com.flexibits.fantastical2.mac/"
    "Database/Fantastical*.fcdata"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def nsdate_to_datetime(nsdate: float) -> datetime:
    """Convert an NSDate timestamp to a Python UTC datetime.

    NSDate stores time as seconds since 2001-01-01 00:00:00 UTC.
    """
    return datetime.fromtimestamp(nsdate + NSDATE_OFFSET, tz=timezone.utc)


def find_database_path() -> str:
    """Auto-discover the Fantastical database file.

    Resolution order:
    1. ``FANTASTICAL_DB_PATH`` environment variable (must exist on disk).
    2. Glob match under the standard Fantastical group container.

    Returns the absolute path as a string.

    Raises:
        FileNotFoundError: If no database file can be located.
    """
    env_path = os.environ.get("FANTASTICAL_DB_PATH")
    if env_path:
        if not Path(env_path).exists():
            raise FileNotFoundError(
                f"FANTASTICAL_DB_PATH points to a file that does not exist: {env_path}"
            )
        return env_path

    matches = glob.glob(_DB_GLOB)
    if not matches:
        raise FileNotFoundError(
            "Could not find the Fantastical database.  Ensure Fantastical is "
            "installed, or set the FANTASTICAL_DB_PATH environment variable."
        )
    return matches[0]


def resolve_uid(
    objects: list,
    ref: plistlib.UID | dict | int | None,
) -> object | None:
    """Resolve an NSKeyedArchiver UID reference into the real object.

    Handles three representations that appear in practice:

    * ``plistlib.UID`` — Python's native keyed-archiver UID type.
    * ``dict`` with a ``CF$UID`` key — legacy / cross-platform representation.
    * ``int`` — plain integer index.

    Index 0 is the ``$null`` sentinel and always returns ``None``.
    """
    if ref is None:
        return None

    if isinstance(ref, plistlib.UID):
        idx = ref.data
    elif isinstance(ref, dict) and "CF$UID" in ref:
        idx = ref["CF$UID"]
    elif isinstance(ref, int):
        idx = ref
    else:
        return None

    if idx == 0:
        return None

    return objects[idx]


def deep_resolve(objects: list, value: object, depth: int = 0) -> object:
    """Recursively resolve every UID in a structure into plain Python values.

    Used for recurrence rules and exception-date arrays where downstream
    code needs the fully-expanded tree, not nested UID references.  Bounded
    depth prevents runaway traversal on pathological blobs.  Strings,
    numbers, and bools pass through unchanged.  The ``$class`` key is
    dropped since it's NSKeyedArchiver bookkeeping.
    """
    if depth > 8:
        return None
    if isinstance(value, plistlib.UID):
        resolved = resolve_uid(objects, value)
        return deep_resolve(objects, resolved, depth + 1)
    if isinstance(value, dict):
        return {
            k: deep_resolve(objects, v, depth + 1)
            for k, v in value.items()
            if k != "$class"
        }
    if isinstance(value, list):
        return [deep_resolve(objects, v, depth + 1) for v in value]
    return value


# ---------------------------------------------------------------------------
# Main database class
# ---------------------------------------------------------------------------


class FantasticalDB:
    """Read-only interface to Fantastical's local YapDatabase SQLite store.

    Parameters:
        db_path: Absolute path to the ``.fcdata`` file.
        exclude_calendars: Optional set of calendar *names* to hide from
            results.  When ``None``, falls back to the
            ``FANTASTICAL_EXCLUDE_CALENDARS`` environment variable (comma-
            separated) and then to :data:`DEFAULT_EXCLUDE_CALENDARS`.
    """

    def __init__(
        self,
        db_path: str,
        exclude_calendars: set[str] | None = None,
    ) -> None:
        uri = f"file:{db_path}?mode=ro"
        self._conn = sqlite3.connect(uri, uri=True)
        self._conn.row_factory = sqlite3.Row

        # Resolve the exclusion set.
        if exclude_calendars is not None:
            self._exclude: set[str] = exclude_calendars
        else:
            env = os.environ.get("FANTASTICAL_EXCLUDE_CALENDARS")
            if env:
                self._exclude = {s.strip() for s in env.split(",") if s.strip()}
            else:
                self._exclude = set(DEFAULT_EXCLUDE_CALENDARS)

        # Resolve recurring-specific exclusion set.
        recurring_env = os.environ.get("FANTASTICAL_RECURRING_EXCLUDE_CALENDARS")
        if recurring_env:
            self._recurring_exclude: set[str] = {
                s.strip() for s in recurring_env.split(",") if s.strip()
            }
        else:
            self._recurring_exclude = set(DEFAULT_RECURRING_EXCLUDE_CALENDARS)

        # Calendar registry: id → display name.
        self._cal_registry: dict[str, str] = {}
        self._load_calendars()

    # -- internal helpers ---------------------------------------------------

    def _load_calendars(self) -> None:
        """Read every ``calendars`` collection blob and populate the registry."""
        cur = self._conn.cursor()
        cur.execute(
            "SELECT key, data FROM database2 WHERE collection = 'calendars'"
        )
        for row in cur.fetchall():
            cal_id: str = row["key"]
            blob: bytes | None = row["data"]
            if blob is None:
                continue
            try:
                plist = plistlib.loads(blob)
                objects = plist.get("$objects", [])
                top = plist.get("$top", {})
                root_ref = top.get("root")
                root = resolve_uid(objects, root_ref)
                if not isinstance(root, dict):
                    continue
                title = resolve_uid(objects, root.get("title"))
                if isinstance(title, str):
                    self._cal_registry[cal_id] = title
            except Exception:  # noqa: BLE001
                # Skip corrupt or unreadable blobs.
                continue

    def _is_excluded(self, cal_id: str) -> bool:
        """Return ``True`` if the calendar should be hidden."""
        name = self._cal_registry.get(cal_id)
        if name is None:
            return False
        return name in self._exclude

    def _is_recurring_excluded(self, cal_id: str) -> bool:
        """Return ``True`` if the calendar should be hidden from recurring results."""
        name = self._cal_registry.get(cal_id)
        if name is None:
            return False
        return name in self._exclude or name in self._recurring_exclude

    # -- event decoding -----------------------------------------------------

    def decode_event(self, blob: bytes, rowid: int) -> dict | None:
        """Decode an NSKeyedArchiver event blob into a plain dict.

        Returns ``None`` if the blob cannot be parsed.
        """
        try:
            plist = plistlib.loads(blob)
            objects = plist.get("$objects", [])
            if len(objects) < 2:
                return None
            root = objects[1]
            if not isinstance(root, dict):
                return None

            title = resolve_uid(objects, root.get("title"))
            location = resolve_uid(objects, root.get("location"))
            notes = resolve_uid(objects, root.get("notes"))
            cal_id = resolve_uid(objects, root.get("calendarIdentifier"))

            # Dates are stored as nested dicts with an NS.time key.
            start_obj = resolve_uid(objects, root.get("startDate"))
            end_obj = resolve_uid(objects, root.get("endDate"))
            start_dt = (
                nsdate_to_datetime(start_obj["NS.time"])
                if isinstance(start_obj, dict) and "NS.time" in start_obj
                else None
            )
            end_dt = (
                nsdate_to_datetime(end_obj["NS.time"])
                if isinstance(end_obj, dict) and "NS.time" in end_obj
                else None
            )

            is_all_day_ref = resolve_uid(objects, root.get("isAllDay"))
            is_all_day = bool(is_all_day_ref) if isinstance(is_all_day_ref, bool) else False

            # Attendees: an NS.objects array of UIDs pointing to attendee dicts.
            attendees_list: list[dict[str, str | None]] = []
            attendees_ref = resolve_uid(objects, root.get("attendees"))
            if isinstance(attendees_ref, dict) and "NS.objects" in attendees_ref:
                for uid in attendees_ref["NS.objects"]:
                    att = resolve_uid(objects, uid)
                    if isinstance(att, dict):
                        attendees_list.append(
                            {
                                "displayName": resolve_uid(
                                    objects, att.get("displayName")
                                ),
                                "emailAddress": resolve_uid(
                                    objects, att.get("emailAddress")
                                ),
                            }
                        )

            # Organizer
            organizer_ref = resolve_uid(objects, root.get("organizer"))
            organizer_dict: dict[str, str | None] | None = None
            if isinstance(organizer_ref, dict):
                organizer_dict = {
                    "displayName": resolve_uid(
                        objects, organizer_ref.get("displayName")
                    ),
                    "emailAddress": resolve_uid(
                        objects, organizer_ref.get("emailAddress")
                    ),
                }

            # Recurrence: capture the full rule dict plus exception/override
            # date lists so the expansion layer can generate occurrences.
            recurrence_ref = resolve_uid(objects, root.get("recurrenceRule"))
            recurring = recurrence_ref is not None and isinstance(
                recurrence_ref, dict
            )
            recurrence_rule = (
                deep_resolve(objects, recurrence_ref) if recurring else None
            )

            exdate_ref = resolve_uid(objects, root.get("recurrenceExceptionDates"))
            rdate_ref = resolve_uid(objects, root.get("recurrenceOccurrenceDates"))

            def _nsdate_array(ref: object) -> list[datetime]:
                if not (isinstance(ref, dict) and "NS.objects" in ref):
                    return []
                out: list[datetime] = []
                for uid in ref["NS.objects"]:
                    entry = resolve_uid(objects, uid)
                    if isinstance(entry, dict) and "NS.time" in entry:
                        out.append(nsdate_to_datetime(entry["NS.time"]))
                return out

            exception_dates = _nsdate_array(exdate_ref)
            occurrence_dates = _nsdate_array(rdate_ref)

            series_end_obj = resolve_uid(objects, root.get("recurrenceEndDate"))
            series_end = (
                nsdate_to_datetime(series_end_obj["NS.time"])
                if isinstance(series_end_obj, dict) and "NS.time" in series_end_obj
                else None
            )

            # The event's timezone drives recurrence expansion: rules like
            # "3rd Thursday of the month" are always anchored to the original
            # authoring zone, not UTC.  The blob stores the full tz data as
            # an NSTimeZone archive; both ``NS.name`` and ``NS.data`` inside
            # are themselves UID references that need resolving before the
            # IANA name is readable.
            tz_obj = deep_resolve(objects, root.get("timeZone"))
            tz_name: str | None = None
            if isinstance(tz_obj, dict):
                candidate = tz_obj.get("NS.name")
                if isinstance(candidate, str):
                    tz_name = candidate

            exchange_uid_val = resolve_uid(objects, root.get("exchangeUID"))
            exchange_uid = (
                exchange_uid_val if isinstance(exchange_uid_val, str) else None
            )

            is_detached_ref = resolve_uid(objects, root.get("isDetached"))
            is_detached = (
                bool(is_detached_ref) if isinstance(is_detached_ref, bool) else False
            )
            inst_obj = resolve_uid(objects, root.get("recurrenceInstanceDate"))
            instance_date = (
                nsdate_to_datetime(inst_obj["NS.time"])
                if isinstance(inst_obj, dict) and "NS.time" in inst_obj
                else None
            )

            conf_ref = resolve_uid(objects, root.get("conferenceType"))
            conference_type = conf_ref if isinstance(conf_ref, int) else 0

            cal_id_str = cal_id if isinstance(cal_id, str) else ""

            return {
                "rowid": rowid,
                "title": title if isinstance(title, str) else "",
                "location": location if isinstance(location, str) else "",
                "notes": notes if isinstance(notes, str) else "",
                "start": start_dt,
                "end": end_dt,
                "calendar_id": cal_id_str,
                "calendar": self._cal_registry.get(cal_id_str, ""),
                "is_all_day": is_all_day,
                "recurring": recurring,
                "recurrence_rule": recurrence_rule,
                "exception_dates": exception_dates,
                "occurrence_dates": occurrence_dates,
                "series_end": series_end,
                "is_detached": is_detached,
                "instance_date": instance_date,
                "tz_name": tz_name,
                "exchange_uid": exchange_uid,
                "attendees": attendees_list,
                "organizer": organizer_dict,
                "conference_type": conference_type,
            }
        except Exception:  # noqa: BLE001
            logger.warning("Failed to decode event blob for rowid %d", rowid)
            return None

    def _decode_with_fts_fallback(
        self, rowid: int, blob: bytes
    ) -> dict | None:
        """Try ``decode_event`` first; fall back to FTS + secondary index data."""
        event = self.decode_event(blob, rowid)
        if event is not None:
            return event

        # Fallback: combine FTS text fields with secondary index metadata.
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT title, location, notes FROM fts_fts WHERE rowid = ?",
                (rowid,),
            )
            fts_row = cur.fetchone()
            cur.execute(
                "SELECT calendarIdentifier, startDate, recurrenceEndDate, "
                "isAllDayOrFloating, recurring, hidden "
                "FROM secondaryIndex_index_calendarItems WHERE rowid = ?",
                (rowid,),
            )
            si_row = cur.fetchone()
            if fts_row is None or si_row is None:
                return None

            cal_id = si_row["calendarIdentifier"] or ""
            start_ns = si_row["startDate"]
            end_ns = si_row["recurrenceEndDate"]

            return {
                "rowid": rowid,
                "title": fts_row["title"] or "",
                "location": fts_row["location"] or "",
                "notes": fts_row["notes"] or "",
                "start": nsdate_to_datetime(start_ns) if start_ns else None,
                "end": nsdate_to_datetime(end_ns) if end_ns else None,
                "calendar_id": cal_id,
                "calendar": self._cal_registry.get(cal_id, ""),
                "is_all_day": bool(si_row["isAllDayOrFloating"]),
                "recurring": bool(si_row["recurring"]),
                "recurrence_rule": None,
                "exception_dates": [],
                "occurrence_dates": [],
                "series_end": None,
                "is_detached": False,
                "instance_date": None,
                "tz_name": None,
                "exchange_uid": None,
                "attendees": [],
                "organizer": None,
                "conference_type": 0,
            }
        except Exception:  # noqa: BLE001
            logger.warning("FTS fallback failed for rowid %d", rowid)
            return None

    # -- public API ---------------------------------------------------------

    def calendar_name(self, cal_id: str) -> str | None:
        """Look up a calendar's display name by its identifier.

        If the identifier is not in the cache, the registry is reloaded once
        in case a new calendar was added since startup.
        """
        name = self._cal_registry.get(cal_id)
        if name is not None:
            return name
        # Refresh and try once more.
        self._load_calendars()
        return self._cal_registry.get(cal_id)

    def get_calendars(self) -> list[dict[str, str | int]]:
        """Return non-excluded calendars with event counts.

        Each dict contains:
        * ``id`` — the calendar identifier string.
        * ``name`` — the human-readable calendar name.
        * ``event_count`` — number of items in the secondary index.
        """
        # Count items per calendar from the secondary index.
        cur = self._conn.cursor()
        cur.execute(
            "SELECT calendarIdentifier, COUNT(*) AS cnt "
            "FROM secondaryIndex_index_calendarItems "
            "GROUP BY calendarIdentifier"
        )
        counts: dict[str, int] = {
            row["calendarIdentifier"]: row["cnt"] for row in cur.fetchall()
        }

        result: list[dict[str, str | int]] = []
        for cal_id, cal_name in self._cal_registry.items():
            if self._is_excluded(cal_id):
                continue
            result.append(
                {
                    "id": cal_id,
                    "name": cal_name,
                    "event_count": counts.get(cal_id, 0),
                }
            )
        return result

    def get_events_in_range(
        self, start: datetime, end: datetime
    ) -> list[dict]:
        """Return decoded events occurring within *[start, end)*.

        Non-recurring events are returned when their ``startDate`` falls in
        the window.  Recurring series are expanded into per-occurrence
        dicts with adjusted ``start``/``end`` times; EXDATEs are removed
        and RDATEs are added.  Detached single-instance events (moved or
        edited occurrences) come through the non-recurring path with their
        new ``startDate``.

        Events from excluded calendars and hidden events are omitted.
        Results are ordered by start date ascending.
        """
        return self._collect_occurrences(start, end, calendar_ids=None)

    def _collect_occurrences(
        self,
        window_start: datetime,
        window_end: datetime,
        calendar_ids: list[str] | None,
    ) -> list[dict]:
        """Shared workhorse for range queries — handles expansion and filters.

        When ``calendar_ids`` is ``None``, all non-excluded calendars are
        included.  When a list is supplied, only those calendar ids are
        queried (the exclusion set is still honoured so callers don't need
        to pre-filter).
        """
        ns_start = window_start.timestamp() - NSDATE_OFFSET
        ns_end = window_end.timestamp() - NSDATE_OFFSET

        cal_clause = ""
        cal_params: tuple = ()
        if calendar_ids is not None:
            if not calendar_ids:
                return []
            placeholders = ",".join("?" for _ in calendar_ids)
            cal_clause = f"AND si.calendarIdentifier IN ({placeholders}) "
            cal_params = tuple(calendar_ids)

        cur = self._conn.cursor()
        results: list[dict] = []

        # --- Pass 1: non-recurring rows whose startDate lies in the window.
        # This also catches detached single-instance events — they have
        # recurring=0 in the index and store their NEW startDate, so range
        # filtering works the same as for one-off events.
        cur.execute(
            "SELECT d.rowid, d.data, si.calendarIdentifier "
            "FROM database2 d "
            "JOIN secondaryIndex_index_calendarItems si ON d.rowid = si.rowid "
            "WHERE (si.recurring IS NULL OR si.recurring = 0) "
            "AND si.startDate >= ? AND si.startDate < ? "
            "AND (si.hidden IS NULL OR si.hidden = 0) "
            f"{cal_clause}"
            "ORDER BY si.startDate ASC",
            (ns_start, ns_end, *cal_params),
        )
        for row in cur.fetchall():
            cal_id: str = row["calendarIdentifier"]
            if self._is_excluded(cal_id):
                continue
            event = self._decode_with_fts_fallback(row["rowid"], row["data"])
            if event is not None:
                results.append(event)

        # --- Pass 2: recurring masters that could produce an occurrence in
        # the window.  A master is eligible when its anchor is before the
        # window's end AND either has no end date or ends at/after the
        # window's start.  Note that recurrenceEndDate uses a far-future
        # sentinel (~4001) to mean "open-ended", so the >= check naturally
        # passes for those rows too.
        cur.execute(
            "SELECT d.rowid, d.data, si.calendarIdentifier "
            "FROM database2 d "
            "JOIN secondaryIndex_index_calendarItems si ON d.rowid = si.rowid "
            "WHERE si.recurring = 1 "
            "AND si.startDate < ? "
            "AND (si.recurrenceEndDate IS NULL OR si.recurrenceEndDate >= ?) "
            "AND (si.hidden IS NULL OR si.hidden = 0) "
            f"{cal_clause}"
            "ORDER BY si.startDate ASC",
            (ns_end, ns_start, *cal_params),
        )
        for row in cur.fetchall():
            cal_id = row["calendarIdentifier"]
            if self._is_excluded(cal_id):
                continue
            master = self._decode_with_fts_fallback(row["rowid"], row["data"])
            if master is None or master.get("start") is None:
                continue
            for occ in self._expand_master(master, window_start, window_end):
                results.append(occ)

        results.sort(
            key=lambda e: e.get("start") or datetime.max.replace(tzinfo=timezone.utc)
        )
        return results

    def _detached_instance_dates(self, master: dict) -> list[datetime]:
        """Return the original-occurrence dates of every detached sibling.

        When a user moves or edits a single occurrence of a recurring series,
        Fantastical creates a separate "detached" event row with
        ``recurring=0``, ``isDetached=true``, and
        ``recurrenceInstanceDate`` pointing at the original date being
        replaced.  The master *usually* also records that date in its
        ``recurrenceExceptionDates`` so the expansion doesn't emit a ghost
        — but not always (observed: moved occurrences on Exchange calendars
        with EXDATE left empty).

        Siblings are linked by shared ``exchangeUID``.  We scan the
        secondary index (which stores ``exchangeUID`` as a column) and
        decode only matching rows — much cheaper than reading every blob.
        Returns an empty list if the master lacks an ``exchangeUID``
        (typical for some local/CalDAV calendars), since we have no
        reliable way to find siblings in that case; those calendars tend
        to use EXDATE anyway.
        """
        exchange_uid = master.get("exchange_uid")
        if not exchange_uid:
            return []

        cur = self._conn.cursor()
        cur.execute(
            "SELECT d.rowid, d.data "
            "FROM database2 d "
            "JOIN secondaryIndex_index_calendarItems si ON d.rowid = si.rowid "
            "WHERE si.exchangeUID = ? "
            "AND (si.recurring IS NULL OR si.recurring = 0) "
            "AND (si.hidden IS NULL OR si.hidden = 0) "
            "AND d.rowid != ?",
            (exchange_uid, master["rowid"]),
        )

        dates: list[datetime] = []
        for row in cur.fetchall():
            sibling = self.decode_event(row["data"], row["rowid"])
            if sibling is None:
                continue
            inst = sibling.get("instance_date")
            if isinstance(inst, datetime):
                dates.append(inst)
        return dates

    def _expand_master(
        self,
        master: dict,
        window_start: datetime,
        window_end: datetime,
    ) -> list[dict]:
        """Turn a recurring-master event dict into per-occurrence event dicts."""
        from .recurrence import expand  # local import to avoid cycles

        anchor_start: datetime = master["start"]
        anchor_end: datetime | None = master.get("end")
        duration = (anchor_end - anchor_start) if anchor_end else None

        exdates = list(master.get("exception_dates") or [])
        # Phase 2 dedup: treat any detached sibling's original date as an
        # extra EXDATE so we don't emit a ghost on top of the moved event.
        exdates.extend(self._detached_instance_dates(master))

        occurrences = expand(
            rule=master.get("recurrence_rule"),
            anchor_start=anchor_start,
            window_start=window_start,
            window_end=window_end,
            exdates=exdates,
            rdates=master.get("occurrence_dates") or [],
            series_end=master.get("series_end"),
            tz_name=master.get("tz_name"),
        )

        if not occurrences:
            return []

        results: list[dict] = []
        for occ_start in occurrences:
            occ = dict(master)
            occ["start"] = occ_start
            occ["end"] = (occ_start + duration) if duration else occ_start
            occ["occurrence_of"] = master["rowid"]
            results.append(occ)
        return results

    def search_events(self, query: str, limit: int = 20) -> list[dict]:
        """Full-text search across event titles, locations, and notes.

        Uses the ``fts_fts`` FTS5 virtual table.  Hidden events and events
        from excluded calendars are omitted.  Results are ordered by start
        date descending.
        """
        cur = self._conn.cursor()
        cur.execute(
            "SELECT d.rowid, d.data, si.calendarIdentifier, si.startDate "
            "FROM fts_fts f "
            "JOIN database2 d ON d.rowid = f.rowid "
            "JOIN secondaryIndex_index_calendarItems si ON si.rowid = f.rowid "
            "WHERE fts_fts MATCH ? "
            "AND (si.hidden IS NULL OR si.hidden = 0) "
            "ORDER BY si.startDate DESC "
            "LIMIT ?",
            (query, limit),
        )

        results: list[dict] = []
        for row in cur.fetchall():
            cal_id: str = row["calendarIdentifier"]
            if self._is_excluded(cal_id):
                continue
            event = self._decode_with_fts_fallback(row["rowid"], row["data"])
            if event is not None:
                results.append(event)

        return results

    def get_events_by_calendar(
        self, calendar_name: str, days: int = 30
    ) -> list[dict]:
        """Return events for a named calendar within a date window.

        Resolves *calendar_name* to one or more calendar identifiers via the
        internal registry.  The date window spans from *now* to
        *now + days* days.  Recurring series are expanded the same way as
        :meth:`get_events_in_range`.  Returns an empty list if the
        calendar name is not found.
        """
        cal_ids = [
            cid
            for cid, name in self._cal_registry.items()
            if name == calendar_name
        ]
        if not cal_ids:
            return []

        now = datetime.now(tz=timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        window_end = today_start + timedelta(days=days)
        return self._collect_occurrences(today_start, window_end, calendar_ids=cal_ids)

    def get_event(self, rowid: int) -> dict | None:
        """Look up a single event by its database rowid.

        Returns ``None`` if no event with the given rowid exists.
        """
        cur = self._conn.cursor()
        cur.execute(
            "SELECT d.rowid, d.data, si.calendarIdentifier "
            "FROM database2 d "
            "JOIN secondaryIndex_index_calendarItems si ON d.rowid = si.rowid "
            "WHERE d.rowid = ?",
            (rowid,),
        )
        row = cur.fetchone()
        if row is None:
            return None

        return self._decode_with_fts_fallback(row["rowid"], row["data"])

    def get_recurring_events(
        self, calendar_name: str | None = None, limit: int = 50
    ) -> list[dict]:
        """Return active recurring events.

        Recurring events store the *original* series start date, not the
        next occurrence, so we cannot filter by ``startDate >= now``.
        Instead we return all recurring events that have no end date or
        whose recurrence end date is in the future.

        Optionally filtered to a single calendar by name.  Excluded
        calendars (both global and recurring-specific) are filtered in
        SQL to avoid consuming the LIMIT with unwanted rows.
        """
        now = datetime.now(tz=timezone.utc)
        ns_now = now.timestamp() - NSDATE_OFFSET

        # Build the set of calendar IDs to exclude in SQL.
        exclude_ids = [
            cid
            for cid, name in self._cal_registry.items()
            if name in self._exclude or name in self._recurring_exclude
        ]

        cur = self._conn.cursor()
        # Over-fetch to compensate for any remaining Python-side filtering.
        fetch_limit = limit * 3

        if calendar_name:
            cal_ids = [
                cid
                for cid, name in self._cal_registry.items()
                if name == calendar_name
            ]
            if not cal_ids:
                return []
            placeholders = ",".join("?" for _ in cal_ids)
            exclude_placeholders = ",".join("?" for _ in exclude_ids)
            cur.execute(
                "SELECT d.rowid, d.data, si.calendarIdentifier "
                "FROM database2 d "
                "JOIN secondaryIndex_index_calendarItems si ON d.rowid = si.rowid "
                f"WHERE si.recurring = 1 "
                f"AND (si.recurrenceEndDate IS NULL OR si.recurrenceEndDate >= ?) "
                f"AND si.calendarIdentifier IN ({placeholders}) "
                + (f"AND si.calendarIdentifier NOT IN ({exclude_placeholders}) "
                   if exclude_ids else "")
                + "AND (si.hidden IS NULL OR si.hidden = 0) "
                "ORDER BY si.startDate ASC "
                "LIMIT ?",
                (ns_now, *cal_ids, *exclude_ids, fetch_limit),
            )
        else:
            exclude_placeholders = ",".join("?" for _ in exclude_ids)
            cur.execute(
                "SELECT d.rowid, d.data, si.calendarIdentifier "
                "FROM database2 d "
                "JOIN secondaryIndex_index_calendarItems si ON d.rowid = si.rowid "
                "WHERE si.recurring = 1 "
                "AND (si.recurrenceEndDate IS NULL OR si.recurrenceEndDate >= ?) "
                + (f"AND si.calendarIdentifier NOT IN ({exclude_placeholders}) "
                   if exclude_ids else "")
                + "AND (si.hidden IS NULL OR si.hidden = 0) "
                "ORDER BY si.startDate ASC "
                "LIMIT ?",
                (ns_now, *exclude_ids, fetch_limit),
            )

        results: list[dict] = []
        for row in cur.fetchall():
            if len(results) >= limit:
                break
            event = self._decode_with_fts_fallback(row["rowid"], row["data"])
            if event is not None:
                results.append(event)

        return results

    def get_pending_invitations(self, limit: int = 20) -> list[dict]:
        """Return events with pending invitations, most recent first.

        Uses the ``invitationNeedsAction`` flag in the secondary index.
        Ordered by start date descending so the most relevant (recent/future)
        invitations appear first.  Hidden events and events from excluded
        calendars are omitted.
        """
        cur = self._conn.cursor()
        fetch_limit = limit * 3
        cur.execute(
            "SELECT d.rowid, d.data, si.calendarIdentifier "
            "FROM database2 d "
            "JOIN secondaryIndex_index_calendarItems si ON d.rowid = si.rowid "
            "WHERE si.invitationNeedsAction = 1 "
            "AND (si.hidden IS NULL OR si.hidden = 0) "
            "ORDER BY si.startDate DESC "
            "LIMIT ?",
            (fetch_limit,),
        )

        results: list[dict] = []
        for row in cur.fetchall():
            if len(results) >= limit:
                break
            cal_id: str = row["calendarIdentifier"]
            if self._is_excluded(cal_id):
                continue
            event = self._decode_with_fts_fallback(row["rowid"], row["data"])
            if event is not None:
                results.append(event)

        return results

    def get_recent_events(self, limit: int = 10) -> list[dict]:
        """Return the most recently added or synced events.

        Uses ``rowid DESC`` ordering as a proxy for creation/sync time.
        Hidden events and events from excluded calendars are omitted.
        Over-fetches to compensate for Python-side calendar exclusion.
        """
        cur = self._conn.cursor()
        # Over-fetch significantly — many high-rowid entries may be from
        # excluded system calendars (Weather, Holidays, etc.).
        fetch_limit = limit * 5
        cur.execute(
            "SELECT d.rowid, d.data, si.calendarIdentifier "
            "FROM database2 d "
            "JOIN secondaryIndex_index_calendarItems si ON d.rowid = si.rowid "
            "WHERE (si.hidden IS NULL OR si.hidden = 0) "
            "ORDER BY d.rowid DESC "
            "LIMIT ?",
            (fetch_limit,),
        )

        results: list[dict] = []
        for row in cur.fetchall():
            if len(results) >= limit:
                break
            cal_id: str = row["calendarIdentifier"]
            if self._is_excluded(cal_id):
                continue
            event = self._decode_with_fts_fallback(row["rowid"], row["data"])
            if event is not None:
                results.append(event)

        return results

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()
