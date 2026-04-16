"""Unit tests for fantastical_mcp.recurrence.expand()."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fantastical_mcp.recurrence import expand


UTC = timezone.utc


def dt(y: int, m: int, d: int, hh: int = 0, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=UTC)


def ns_date(value: datetime) -> dict:
    """Encode a datetime the way NSKeyedArchiver represents it in the blob."""
    return {"NS.time": value.timestamp() - 978307200}


# ---------------------------------------------------------------------------
# Frequency / interval / BYDAY
# ---------------------------------------------------------------------------


def test_weekly_on_weekdays_expands_across_window():
    """Lunch-style: type=2, daysOfTheWeek=Mon-Fri, interval=1."""
    rule = {
        "type": 2,
        "interval": 1,
        "daysOfTheWeek": {
            "NS.objects": [
                {"dayOfTheWeek": 2, "weekNumber": 0},  # Mon
                {"dayOfTheWeek": 3, "weekNumber": 0},
                {"dayOfTheWeek": 4, "weekNumber": 0},
                {"dayOfTheWeek": 5, "weekNumber": 0},
                {"dayOfTheWeek": 6, "weekNumber": 0},  # Fri
            ]
        },
        "firstDayOfTheWeek": 1,
        "occurrenceCount": 0,
    }
    # Anchor is a Monday.  Window covers a full business week.
    occurrences = expand(
        rule,
        anchor_start=dt(2025, 1, 6, 12, 0),  # Mon
        window_start=dt(2026, 4, 13),  # Mon
        window_end=dt(2026, 4, 18),  # Sat (exclusive)
    )
    # Expect Mon–Fri at 12:00.
    assert occurrences == [
        dt(2026, 4, 13, 12, 0),
        dt(2026, 4, 14, 12, 0),
        dt(2026, 4, 15, 12, 0),
        dt(2026, 4, 16, 12, 0),
        dt(2026, 4, 17, 12, 0),
    ]


def test_fortnightly_single_weekday():
    """Busy-style: type=2, daysOfTheWeek=Thu, interval=2."""
    rule = {
        "type": 2,
        "interval": 2,
        "daysOfTheWeek": {
            "NS.objects": [{"dayOfTheWeek": 5, "weekNumber": 0}]
        },
        "firstDayOfTheWeek": 2,
    }
    # Anchor: Thu 2026-04-02.  Fortnightly → 02, 16, 30 Apr.
    occurrences = expand(
        rule,
        anchor_start=dt(2026, 4, 2, 7, 30),
        window_start=dt(2026, 4, 1),
        window_end=dt(2026, 5, 1),
    )
    assert occurrences == [
        dt(2026, 4, 2, 7, 30),
        dt(2026, 4, 16, 7, 30),
        dt(2026, 4, 30, 7, 30),
    ]


def test_daily_interval_three():
    rule = {"type": 0, "interval": 3}
    occurrences = expand(
        rule,
        anchor_start=dt(2026, 4, 1, 9, 0),
        window_start=dt(2026, 4, 1),
        window_end=dt(2026, 4, 15),
    )
    # Every 3rd day starting Apr 1: 1, 4, 7, 10, 13.
    assert occurrences == [
        dt(2026, 4, 1, 9, 0),
        dt(2026, 4, 4, 9, 0),
        dt(2026, 4, 7, 9, 0),
        dt(2026, 4, 10, 9, 0),
        dt(2026, 4, 13, 9, 0),
    ]


def test_monthly_by_day_number():
    rule = {
        "type": 3,
        "interval": 1,
        "daysOfTheMonth": {"NS.objects": [15]},
    }
    occurrences = expand(
        rule,
        anchor_start=dt(2026, 1, 15, 10, 0),
        window_start=dt(2026, 4, 1),
        window_end=dt(2026, 7, 1),
    )
    assert occurrences == [
        dt(2026, 4, 15, 10, 0),
        dt(2026, 5, 15, 10, 0),
        dt(2026, 6, 15, 10, 0),
    ]


def test_monthly_nth_weekday():
    """Second Tuesday of every month — weekNumber=2, dayOfTheWeek=3."""
    rule = {
        "type": 3,
        "interval": 1,
        "daysOfTheWeek": {
            "NS.objects": [{"dayOfTheWeek": 3, "weekNumber": 2}]
        },
    }
    occurrences = expand(
        rule,
        anchor_start=dt(2026, 1, 13, 15, 0),  # 2nd Tue of Jan 2026
        window_start=dt(2026, 4, 1),
        window_end=dt(2026, 7, 1),
    )
    assert occurrences == [
        dt(2026, 4, 14, 15, 0),  # 2nd Tue of Apr
        dt(2026, 5, 12, 15, 0),
        dt(2026, 6, 9, 15, 0),
    ]


def test_yearly_new_years_day():
    rule = {"type": 4, "interval": 1}
    occurrences = expand(
        rule,
        anchor_start=dt(2000, 1, 1),
        window_start=dt(2026, 1, 1),
        window_end=dt(2028, 1, 1),
    )
    assert occurrences == [dt(2026, 1, 1), dt(2027, 1, 1)]


# ---------------------------------------------------------------------------
# EXDATE / RDATE / UNTIL / COUNT
# ---------------------------------------------------------------------------


def test_exdate_removes_matching_occurrence():
    rule = {
        "type": 2,
        "interval": 1,
        "daysOfTheWeek": {
            "NS.objects": [{"dayOfTheWeek": 4, "weekNumber": 0}]  # Wed
        },
    }
    skipped = dt(2026, 4, 15, 9, 0)
    occurrences = expand(
        rule,
        anchor_start=dt(2026, 4, 1, 9, 0),
        window_start=dt(2026, 4, 1),
        window_end=dt(2026, 4, 30),
        exdates=[skipped],
    )
    assert skipped not in occurrences
    assert dt(2026, 4, 8, 9, 0) in occurrences
    assert dt(2026, 4, 22, 9, 0) in occurrences


def test_rdate_adds_extra_occurrence():
    rule = {
        "type": 2,
        "interval": 1,
        "daysOfTheWeek": {
            "NS.objects": [{"dayOfTheWeek": 4, "weekNumber": 0}]
        },
    }
    extra = dt(2026, 4, 10, 9, 0)  # A Friday outside the rule
    occurrences = expand(
        rule,
        anchor_start=dt(2026, 4, 1, 9, 0),
        window_start=dt(2026, 4, 1),
        window_end=dt(2026, 4, 30),
        rdates=[extra],
    )
    assert extra in occurrences


def test_exdate_wins_over_rdate():
    extra = dt(2026, 4, 10, 9, 0)
    occurrences = expand(
        rule={"type": 2, "interval": 1, "daysOfTheWeek": {"NS.objects": [{"dayOfTheWeek": 4, "weekNumber": 0}]}},
        anchor_start=dt(2026, 4, 1, 9, 0),
        window_start=dt(2026, 4, 1),
        window_end=dt(2026, 4, 30),
        rdates=[extra],
        exdates=[extra],
    )
    assert extra not in occurrences


def test_series_end_caps_expansion():
    rule = {
        "type": 2,
        "interval": 1,
        "daysOfTheWeek": {
            "NS.objects": [{"dayOfTheWeek": 4, "weekNumber": 0}]
        },
    }
    occurrences = expand(
        rule,
        anchor_start=dt(2026, 4, 1, 9, 0),
        window_start=dt(2026, 4, 1),
        window_end=dt(2026, 6, 1),
        series_end=dt(2026, 4, 20),
    )
    assert occurrences == [dt(2026, 4, 1, 9, 0), dt(2026, 4, 8, 9, 0), dt(2026, 4, 15, 9, 0)]


def test_rule_endDate_takes_precedence_over_series_end():
    rule = {
        "type": 2,
        "interval": 1,
        "daysOfTheWeek": {
            "NS.objects": [{"dayOfTheWeek": 4, "weekNumber": 0}]
        },
        "endDate": ns_date(dt(2026, 4, 10)),
    }
    occurrences = expand(
        rule,
        anchor_start=dt(2026, 4, 1, 9, 0),
        window_start=dt(2026, 4, 1),
        window_end=dt(2026, 6, 1),
        series_end=dt(2026, 5, 1),  # should be ignored
    )
    # Only Apr 1 and Apr 8 — Apr 15 is past rule endDate.
    assert occurrences == [dt(2026, 4, 1, 9, 0), dt(2026, 4, 8, 9, 0)]


def test_occurrence_count_honoured():
    rule = {
        "type": 0,
        "interval": 1,
        "occurrenceCount": 3,
    }
    occurrences = expand(
        rule,
        anchor_start=dt(2026, 4, 1, 9, 0),
        window_start=dt(2026, 4, 1),
        window_end=dt(2026, 5, 1),
    )
    assert occurrences == [
        dt(2026, 4, 1, 9, 0),
        dt(2026, 4, 2, 9, 0),
        dt(2026, 4, 3, 9, 0),
    ]


# ---------------------------------------------------------------------------
# Window edges
# ---------------------------------------------------------------------------


def test_window_end_exclusive():
    """An occurrence exactly at window_end must NOT be included."""
    rule = {"type": 0, "interval": 1}
    occurrences = expand(
        rule,
        anchor_start=dt(2026, 4, 1, 0, 0),
        window_start=dt(2026, 4, 1),
        window_end=dt(2026, 4, 2),
    )
    assert occurrences == [dt(2026, 4, 1, 0, 0)]


def test_window_entirely_before_anchor_returns_empty():
    rule = {"type": 0, "interval": 1}
    occurrences = expand(
        rule,
        anchor_start=dt(2026, 4, 1),
        window_start=dt(2025, 1, 1),
        window_end=dt(2025, 2, 1),
    )
    assert occurrences == []


def test_null_sentinel_end_date_treated_as_open():
    rule = {
        "type": 0,
        "interval": 1,
        "endDate": "$null",
    }
    occurrences = expand(
        rule,
        anchor_start=dt(2026, 4, 1),
        window_start=dt(2026, 4, 1),
        window_end=dt(2026, 4, 4),
    )
    assert len(occurrences) == 3


def test_monthly_nth_weekday_respects_event_timezone():
    """Regression: "3rd Thursday" must evaluate in the event's own TZ.

    Anchor is Wed 23:10 UTC = Thu 09:40 Australia/Adelaide.  Without the
    tz_name hint the expander would emit the 3rd Thursday in UTC
    (one day later in AU), which is how we originally missed Jason's
    10:00 meeting on 2026-04-16 AU.
    """
    rule = {
        "type": 3,
        "interval": 1,
        "daysOfTheWeek": {
            "NS.objects": [{"dayOfTheWeek": 5, "weekNumber": 3}]
        },
        "occurrenceCount": 12,
    }
    anchor_utc = datetime(2025, 10, 15, 23, 10, tzinfo=UTC)  # Thu AU, Wed UTC

    # Use a wide UTC window covering all of 2026-04-16 AU.
    occs = expand(
        rule,
        anchor_start=anchor_utc,
        window_start=datetime(2026, 4, 15, 14, 30, tzinfo=UTC),  # 00:00 ACST
        window_end=datetime(2026, 4, 16, 14, 30, tzinfo=UTC),   # 00:00 next day ACST
        tz_name="Australia/Adelaide",
    )
    # The 7th occurrence should land on 2026-04-16 in Adelaide (ACST in
    # April, UTC+09:30).  Anchor's local clock time of 09:40 → 00:10 UTC.
    assert datetime(2026, 4, 16, 0, 10, tzinfo=UTC) in occs


def test_none_rule_returns_only_rdates():
    extra = dt(2026, 4, 10, 9, 0)
    occurrences = expand(
        rule=None,  # type: ignore[arg-type]
        anchor_start=dt(2026, 4, 1, 9, 0),
        window_start=dt(2026, 4, 1),
        window_end=dt(2026, 4, 30),
        rdates=[extra, dt(2025, 1, 1)],  # second RDATE outside window
    )
    assert occurrences == [extra]
