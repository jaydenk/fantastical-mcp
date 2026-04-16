"""Expand Fantastical's EKRecurrenceRule blobs into concrete occurrences.

Fantastical's YapDatabase stores events with their ``EKRecurrenceRule``
sub-object persisted verbatim via ``NSKeyedArchiver``.  The secondary index
only holds the *series anchor* (the original first occurrence), which means
range queries miss every recurring event whose anchor isn't itself inside
the requested window.  This module turns a rule dict into concrete
occurrence ``datetime``\\s so callers can answer "what's on today?"
correctly.

The rule layout observed in practice:

``type``
    Frequency.  ``0``/``1`` = daily, ``2`` = weekly, ``3`` = monthly,
    ``4`` = yearly.
``interval``
    Every N periods (e.g. ``2`` = fortnightly).
``daysOfTheWeek``
    Optional ``NS.objects`` list of ``{dayOfTheWeek: 1..7, weekNumber: N}``.
    ``dayOfTheWeek`` follows ``EKWeekday`` — Sunday=1 … Saturday=7.
    Non-zero ``weekNumber`` means "Nth weekday of the month" (negative
    values count from the end).
``daysOfTheMonth`` / ``daysOfTheYear`` / ``weeksOfTheYear`` / ``monthsOfTheYear``
    ``NS.objects`` lists of ints — BYMONTHDAY / BYYEARDAY / BYWEEKNO /
    BYMONTH respectively.
``setPositions``
    ``NS.objects`` list of ints — BYSETPOS.
``occurrenceCount``
    COUNT limit (``0`` = unlimited).
``endDate``
    UNTIL datetime (nullable).
"""

from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil import rrule

# ---------------------------------------------------------------------------
# Enum mappings
# ---------------------------------------------------------------------------

# EKWeekday (Sunday=1 … Saturday=7) → dateutil weekday constant (Mon=0 … Sun=6).
_EK_WEEKDAY_TO_DATEUTIL = {
    1: rrule.SU,
    2: rrule.MO,
    3: rrule.TU,
    4: rrule.WE,
    5: rrule.TH,
    6: rrule.FR,
    7: rrule.SA,
}

# Fantastical's type enum → dateutil frequency.
# Verified against real data: Lunch (type=2, daysOfTheWeek=Mon-Fri, interval=1)
# and fortnightly Busy (type=2, daysOfTheWeek=Thu, interval=2) both weekly.
_TYPE_TO_FREQ = {
    0: rrule.DAILY,
    1: rrule.DAILY,
    2: rrule.WEEKLY,
    3: rrule.MONTHLY,
    4: rrule.YEARLY,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_null(value: object) -> bool:
    """Return True for the ``'$null'`` sentinel or actual None."""
    return value is None or value == "$null"


def _ns_objects(value: object) -> list:
    """Extract an NSKeyedArchiver array's ``NS.objects`` list, or ``[]``."""
    if isinstance(value, dict) and "NS.objects" in value:
        return list(value["NS.objects"])
    return []


def _weekday_rules(days_of_the_week: object) -> list:
    """Translate ``daysOfTheWeek`` entries into dateutil weekday objects."""
    result = []
    for entry in _ns_objects(days_of_the_week):
        if not isinstance(entry, dict):
            continue
        ek = entry.get("dayOfTheWeek")
        if ek not in _EK_WEEKDAY_TO_DATEUTIL:
            continue
        weekday = _EK_WEEKDAY_TO_DATEUTIL[ek]
        week_number = entry.get("weekNumber", 0) or 0
        result.append(weekday(week_number) if week_number else weekday)
    return result


def _int_list(value: object) -> list[int]:
    """Return a list of ints from an ``NS.objects`` array, else ``[]``."""
    return [v for v in _ns_objects(value) if isinstance(v, int)]


def _nsdate_list_to_datetimes(value: object) -> list[datetime]:
    """Convert an ``NS.objects`` list of ``{NS.time: float}`` into UTC datetimes."""
    from .db import nsdate_to_datetime  # local import to avoid cycles

    out: list[datetime] = []
    for entry in _ns_objects(value):
        if isinstance(entry, dict) and "NS.time" in entry:
            out.append(nsdate_to_datetime(entry["NS.time"]))
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _resolve_tz(tz_name: str | None) -> tzinfo:
    """Return a tzinfo for ``tz_name`` or UTC if unknown/missing."""
    if not tz_name:
        return timezone.utc
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return timezone.utc


def expand(
    rule: dict,
    anchor_start: datetime,
    window_start: datetime,
    window_end: datetime,
    exdates: Iterable[datetime] = (),
    rdates: Iterable[datetime] = (),
    series_end: datetime | None = None,
    tz_name: str | None = None,
) -> list[datetime]:
    """Return every recurrence occurrence ``start`` in ``[window_start, window_end)``.

    All ``datetime`` inputs must be timezone-aware; outputs are UTC.

    Expansion happens in the series' authoring timezone (``tz_name``) so
    that rules like "3rd Thursday of the month" land on the correct local
    day even when that day straddles the UTC boundary (e.g. a 10:00
    Adelaide meeting whose UTC anchor is 23:30 the previous day).  Results
    are converted back to UTC before being returned and compared against
    the window.

    Parameters:
        rule: The ``recurrenceRule`` dict as decoded from the event blob.
            May be ``None`` to represent "no rule" (returns RDATEs only).
        anchor_start: The series' original first-occurrence start (UTC).
        window_start: Inclusive lower bound of the query window (UTC).
        window_end: Exclusive upper bound of the query window (UTC).
        exdates: Occurrences to skip (EXDATE).  Compared by exact equality
            to generated occurrence datetimes.
        rdates: Extra occurrences to add (RDATE) — emitted verbatim when
            they fall inside the window.
        series_end: Optional absolute series UNTIL date (from
            ``recurrenceEndDate`` on the root event).  Caps generation
            independently of any ``endDate`` inside the rule.
        tz_name: IANA timezone name (e.g. ``"Australia/Adelaide"``) taken
            from the event's ``timeZone`` field.  ``None`` / unknown zones
            fall back to UTC, which is the right default for events that
            were authored as floating or UTC-native.

    Returns occurrence start datetimes sorted ascending.  Duplicates are
    removed; EXDATEs are removed last so they also filter RDATEs.
    """
    occurrences: set[datetime] = set()

    # RDATEs first — they apply even if ``rule`` itself is None.
    for dt in rdates:
        if window_start <= dt < window_end:
            occurrences.add(dt)

    if rule and not _is_null(rule):
        zone = _resolve_tz(tz_name)
        local_anchor = anchor_start.astimezone(zone)
        local_window_start = window_start.astimezone(zone)
        local_window_end = window_end.astimezone(zone)

        freq = _TYPE_TO_FREQ.get(rule.get("type"), rrule.WEEKLY)
        interval = rule.get("interval") or 1

        kwargs: dict[str, object] = {
            "freq": freq,
            "dtstart": local_anchor,
            "interval": interval,
        }

        count = rule.get("occurrenceCount") or 0
        if count:
            # RFC 5545 (and dateutil) disallows setting both COUNT and UNTIL
            # on the same rule.  COUNT is always authoritative when present.
            kwargs["count"] = count
        else:
            # UNTIL: prefer rule's own endDate; fall back to root-level
            # series_end which Fantastical may store separately.
            until: datetime | None = None
            end_obj = rule.get("endDate")
            if isinstance(end_obj, dict) and "NS.time" in end_obj:
                from .db import nsdate_to_datetime  # local import

                until = nsdate_to_datetime(end_obj["NS.time"])
            elif series_end is not None:
                until = series_end
            if until is not None:
                kwargs["until"] = until.astimezone(zone)

        byweekday = _weekday_rules(rule.get("daysOfTheWeek"))
        if byweekday:
            kwargs["byweekday"] = byweekday

        by_month_day = _int_list(rule.get("daysOfTheMonth"))
        if by_month_day:
            kwargs["bymonthday"] = by_month_day

        by_year_day = _int_list(rule.get("daysOfTheYear"))
        if by_year_day:
            kwargs["byyearday"] = by_year_day

        by_week_no = _int_list(rule.get("weeksOfTheYear"))
        if by_week_no:
            kwargs["byweekno"] = by_week_no

        by_month = _int_list(rule.get("monthsOfTheYear"))
        if by_month:
            kwargs["bymonth"] = by_month

        by_set_pos = _int_list(rule.get("setPositions"))
        if by_set_pos:
            kwargs["bysetpos"] = by_set_pos

        wkst = rule.get("firstDayOfTheWeek")
        if isinstance(wkst, int) and wkst in _EK_WEEKDAY_TO_DATEUTIL:
            kwargs["wkst"] = _EK_WEEKDAY_TO_DATEUTIL[wkst]

        try:
            rr = rrule.rrule(**kwargs)
            # ``between`` is inclusive at both ends by default; we want
            # [window_start, window_end), so we filter the upper bound
            # ourselves to avoid accidentally including window_end.
            for dt in rr.between(
                local_window_start, local_window_end, inc=True
            ):
                utc_dt = dt.astimezone(timezone.utc)
                if utc_dt >= window_end:
                    continue
                occurrences.add(utc_dt)
        except (ValueError, TypeError):
            # Malformed rule — skip expansion, fall through to RDATE/EXDATE.
            pass

    for dt in exdates:
        occurrences.discard(dt)

    return sorted(occurrences)
