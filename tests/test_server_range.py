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
    assert start == _local_midnight_utc(2026, 5, 28)
    # End is exclusive midnight AFTER the 10th, so all of the 10th is included.
    assert end == _local_midnight_utc(2026, 6, 11)


def test_relative_window_uses_injected_now():
    now = _local_midnight_utc(2026, 6, 8) + timedelta(hours=12)  # noon local, 8 Jun
    win = _resolve_range_window(None, None, 14, now)
    assert isinstance(win, tuple)
    start, end = win
    assert start == _local_midnight_utc(2026, 5, 25)  # 14 days before 8 Jun
    assert end == _local_midnight_utc(2026, 6, 9)      # end of today (8 Jun)


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
