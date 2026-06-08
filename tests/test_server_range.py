"""Unit tests for the get_events_in_range window resolver (_resolve_range_window)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fantastical_mcp.server import _resolve_range_window

# Local timezone, matching the pattern in test_formatters.py / test_db.py, so
# expected windows are expressed as UTC instants of predictable local times.
_LOCAL_TZ = datetime.now().astimezone().tzinfo


def _local_midnight_utc(year: int, month: int, day: int) -> datetime:
    """UTC instant corresponding to local midnight on the given date."""
    return datetime(year, month, day, tzinfo=_LOCAL_TZ).astimezone(timezone.utc)


def test_absolute_window_end_is_inclusive():
    win = _resolve_range_window(
        "2026-05-28", "2026-06-10", None, datetime.now(timezone.utc)
    )
    assert isinstance(win, tuple)
    start, end = win
    # 28 May -> local midnight after 10 Jun (inclusive end) = a 14-day span.
    # Asserting the span (not absolute UTC instants) keeps this DST-independent.
    assert end - start == timedelta(days=14)
    assert start.tzinfo == timezone.utc
    assert end.tzinfo == timezone.utc


def test_relative_window_uses_injected_now():
    now = _local_midnight_utc(2026, 6, 8) + timedelta(hours=12)  # midday 8 Jun local
    win = _resolve_range_window(None, None, 14, now)
    assert isinstance(win, tuple)
    start, end = win
    # last 14 days through end of today = a 15-day span; window brackets `now`.
    assert end - start == timedelta(days=15)
    assert start < now < end
    assert start.tzinfo == timezone.utc
    assert end.tzinfo == timezone.utc


def test_both_modes_is_error():
    out = _resolve_range_window(
        "2026-05-28", "2026-06-10", 14, datetime.now(timezone.utc)
    )
    assert isinstance(out, str)
    assert "not both" in out


def test_only_start_is_error():
    out = _resolve_range_window("2026-05-28", None, None, datetime.now(timezone.utc))
    assert isinstance(out, str)
    assert "both start and end" in out


def test_bad_date_is_error():
    out = _resolve_range_window("2026-13-99", "2026-06-10", None, datetime.now(timezone.utc))
    assert isinstance(out, str)
    assert "Invalid date format" in out


def test_end_before_start_is_error():
    out = _resolve_range_window("2026-06-10", "2026-05-28", None, datetime.now(timezone.utc))
    assert isinstance(out, str)
    assert "before start" in out


def test_zero_days_back_is_error():
    out = _resolve_range_window(None, None, 0, datetime.now(timezone.utc))
    assert isinstance(out, str)
    assert "positive integer" in out


def test_range_too_large_is_error():
    out = _resolve_range_window("2020-01-01", "2026-01-01", None, datetime.now(timezone.utc))
    assert isinstance(out, str)
    assert "Range too large" in out


def test_neither_mode_is_usage():
    out = _resolve_range_window(None, None, None, datetime.now(timezone.utc))
    assert isinstance(out, str)
    assert "Specify either" in out


def test_only_end_is_error():
    out = _resolve_range_window(None, "2026-06-10", None, datetime.now(timezone.utc))
    assert isinstance(out, str)
    assert "both start and end" in out


def test_negative_days_back_is_error():
    out = _resolve_range_window(None, None, -5, datetime.now(timezone.utc))
    assert isinstance(out, str)
    assert "positive integer" in out


def test_days_back_at_max_is_allowed():
    win = _resolve_range_window(None, None, 365, datetime.now(timezone.utc))
    assert isinstance(win, tuple)


def test_days_back_over_max_is_error():
    out = _resolve_range_window(None, None, 366, datetime.now(timezone.utc))
    assert isinstance(out, str)
    assert "Range too large" in out
