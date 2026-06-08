# get_events_in_range Tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `get_events_in_range` MCP tool that returns clean, optionally calendar-scoped events for an arbitrary date window (past or future), specified by absolute dates or a relative day count.

**Architecture:** A pure validation/parsing helper (`_resolve_range_window`) resolves the two mutually-exclusive window modes to a UTC `(start, end)` tuple or an error string. The tool then calls `db.get_events_in_range(start, end, calendar_name=...)` — the existing clean engine (`_collect_occurrences`: `hidden` filter + recurring expansion + detached-instance dedup) gains one backward-compatible `calendar_name` parameter. Output reuses `format_events_by_date`. No aggregation, no cross-calendar dedup — calendar scoping alone removes the cross-calendar mirroring.

**Tech Stack:** Python 3.12, FastMCP, pytest / pytest-asyncio, `uv`. Reads Fantastical's local SQLite (`.fcdata`).

**Spec:** `docs/superpowers/specs/2026-06-06-get-events-in-range-tool-design.md`

---

## File Structure

- **Modify** `src/fantastical_mcp/db.py` — add `calendar_name: str | None = None` to `get_events_in_range` (one method, ~10 lines). Responsibility unchanged: read-only range queries over the clean engine.
- **Modify** `src/fantastical_mcp/server.py` — add the pure `_resolve_range_window` helper and the `get_events_in_range` `@mcp.tool`. Responsibility unchanged: tool definitions + arg validation.
- **Create** `tests/test_server_range.py` — unit tests for `_resolve_range_window` (no Fantastical needed).
- **Modify** `tests/test_db.py` — add a `TestGetEventsInRangeCalendarScoping` class (reuses existing `test_db` fixture + `_create_event_blob` / `_insert_event` helpers).
- **Modify** `tests/integration/test_live.py` — one live end-to-end scoping test.
- **Modify** `docs/tools.md`, `README.md`, `CLAUDE.md`, `TODO.md` — documentation.

Run unit tests with: `pytest tests/ --ignore=tests/integration -v`
Run everything (needs Fantastical): `pytest -v`

---

### Task 1: Pure window-resolution helper `_resolve_range_window`

**Files:**
- Create: `tests/test_server_range.py`
- Modify: `src/fantastical_mcp/server.py` (add helper after `_get_db()`, before the first `@mcp.tool`)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_server_range.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_server_range.py -v`
Expected: FAIL — `ImportError: cannot import name '_resolve_range_window' from 'fantastical_mcp.server'`.

- [ ] **Step 3: Implement the helper**

In `src/fantastical_mcp/server.py`, add this function immediately after `_get_db()` and before the first `@mcp.tool` decorator. `datetime`, `timedelta`, `timezone`, and `MAX_DAYS` are already imported/defined at the top of the file.

```python
def _resolve_range_window(
    start: str | None,
    end: str | None,
    days_back: int | None,
    now: datetime,
) -> tuple[datetime, datetime] | str:
    """Resolve absolute/relative range arguments to a UTC ``(start, end)`` window.

    Exactly one mode must be used:

    * Absolute — ``start`` and ``end`` as ``"YYYY-MM-DD"``. ``end`` is inclusive
      of the whole day (the window extends to local midnight after ``end``).
    * Relative — ``days_back`` (positive int): from local midnight ``days_back``
      days ago through the end of today.

    Returns a ``(window_start_utc, window_end_utc)`` tuple, or an error/usage
    string when the arguments are ambiguous or invalid. ``now`` must be a
    timezone-aware datetime (injected so the relative window is testable).
    """
    has_absolute = start is not None or end is not None
    has_relative = days_back is not None

    if has_absolute and has_relative:
        return (
            "Use either absolute dates (start, end) or a relative window "
            "(days_back), not both."
        )

    if has_absolute:
        if start is None or end is None:
            return "Absolute mode needs both start and end in YYYY-MM-DD format."
        try:
            start_naive = datetime.strptime(start, "%Y-%m-%d")
        except ValueError:
            return f"Invalid date format: {start}. Use YYYY-MM-DD."
        try:
            end_naive = datetime.strptime(end, "%Y-%m-%d")
        except ValueError:
            return f"Invalid date format: {end}. Use YYYY-MM-DD."
        if end_naive < start_naive:
            return f"end ({end}) is before start ({start})."
        # Treat the parsed dates as local-clock midnights (matches get_availability).
        local_start = start_naive.astimezone().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        local_end = (end_naive + timedelta(days=1)).astimezone().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    elif has_relative:
        if days_back <= 0:
            return "days_back must be a positive integer."
        local_today = now.astimezone().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        local_start = local_today - timedelta(days=days_back)
        local_end = local_today + timedelta(days=1)
    else:
        return (
            "Specify either absolute dates (start and end, YYYY-MM-DD) or a "
            "relative window (days_back)."
        )

    if (local_end - local_start).days > MAX_DAYS:
        return f"Range too large (max {MAX_DAYS} days)."

    return (
        local_start.astimezone(timezone.utc),
        local_end.astimezone(timezone.utc),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_server_range.py -v`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
git add tests/test_server_range.py src/fantastical_mcp/server.py
git commit -m "feat: add _resolve_range_window window resolver with validation"
```

---

### Task 2: Scope `db.get_events_in_range` to a named calendar

**Files:**
- Modify: `src/fantastical_mcp/db.py` (the `get_events_in_range` method, ~line 503)
- Test: `tests/test_db.py` (new test class near the other range tests)

- [ ] **Step 1: Write the failing tests**

In `tests/test_db.py`, append this class (it reuses the module's existing `test_db` fixture, `_LOCAL_TZ`, `_create_event_blob`, and `_insert_event` helpers — all already defined in this file):

```python
class TestGetEventsInRangeCalendarScoping:
    """Verify the optional calendar_name parameter on get_events_in_range."""

    def _seed_two_calendars(self, db_path):
        """Seed one timed event on 'Work' (abc123) and one on 'Personal' (def456).

        Returns the (start_utc, end_utc) of the seeded events.
        """
        conn = sqlite3.connect(str(db_path))
        noon_local = datetime.now(tz=_LOCAL_TZ).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        start = noon_local.astimezone(timezone.utc)
        end = (noon_local + timedelta(hours=1)).astimezone(timezone.utc)
        for rowid, cal_id, title in [
            (400, "abc123", "Work Shift"),
            (401, "def456", "Personal Lunch"),
        ]:
            blob = _create_event_blob(
                title=title, calendar_id=cal_id, start=start, end=end
            )
            _insert_event(
                conn, rowid=rowid, cal_id=cal_id, blob=blob,
                start=start, end=end, title=title,
            )
        conn.commit()
        conn.close()
        return start, end

    def test_scopes_to_named_calendar(self, test_db):
        start, end = self._seed_two_calendars(test_db)
        db = FantasticalDB(str(test_db))
        try:
            events = db.get_events_in_range(
                start - timedelta(hours=1), end + timedelta(hours=1),
                calendar_name="Work",
            )
            titles = [e["title"] for e in events]
            assert "Work Shift" in titles
            assert "Personal Lunch" not in titles
        finally:
            db.close()

    def test_all_calendars_when_name_omitted(self, test_db):
        start, end = self._seed_two_calendars(test_db)
        db = FantasticalDB(str(test_db))
        try:
            events = db.get_events_in_range(
                start - timedelta(hours=1), end + timedelta(hours=1)
            )
            titles = [e["title"] for e in events]
            assert "Work Shift" in titles
            assert "Personal Lunch" in titles
        finally:
            db.close()

    def test_unknown_calendar_returns_empty(self, test_db):
        start, end = self._seed_two_calendars(test_db)
        db = FantasticalDB(str(test_db))
        try:
            events = db.get_events_in_range(
                start - timedelta(hours=1), end + timedelta(hours=1),
                calendar_name="Nonexistent",
            )
            assert events == []
        finally:
            db.close()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_db.py::TestGetEventsInRangeCalendarScoping -v`
Expected: FAIL — `TypeError: get_events_in_range() got an unexpected keyword argument 'calendar_name'`.

- [ ] **Step 3: Implement the change**

In `src/fantastical_mcp/db.py`, replace the existing `get_events_in_range` method (currently ends with `return self._collect_occurrences(start, end, calendar_ids=None)`) with:

```python
    def get_events_in_range(
        self, start: datetime, end: datetime, calendar_name: str | None = None
    ) -> list[dict]:
        """Return decoded events occurring within *[start, end)*.

        Non-recurring events are returned when their ``startDate`` falls in
        the window.  Recurring series are expanded into per-occurrence
        dicts with adjusted ``start``/``end`` times; EXDATEs are removed
        and RDATEs are added.  Detached single-instance events (moved or
        edited occurrences) come through the non-recurring path with their
        new ``startDate``.

        When ``calendar_name`` is given, results are scoped to that calendar
        (resolved to its identifier(s) via the registry); an unknown name
        yields an empty list.  When ``None`` (default), all non-excluded
        calendars are queried — the original behaviour.

        Events from excluded calendars and hidden events are omitted.
        Results are ordered by start date ascending.
        """
        calendar_ids: list[str] | None = None
        if calendar_name is not None:
            calendar_ids = [
                cid
                for cid, name in self._cal_registry.items()
                if name == calendar_name
            ]
            if not calendar_ids:
                return []
        return self._collect_occurrences(start, end, calendar_ids=calendar_ids)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_db.py::TestGetEventsInRangeCalendarScoping -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Run the full unit suite to confirm no regression**

Run: `pytest tests/ --ignore=tests/integration -v`
Expected: PASS (all existing tests + the new ones; existing callers of `get_events_in_range` are unaffected because `calendar_name` defaults to `None`).

- [ ] **Step 6: Commit**

```bash
git add src/fantastical_mcp/db.py tests/test_db.py
git commit -m "feat: scope db.get_events_in_range to an optional named calendar"
```

---

### Task 3: Wire the `get_events_in_range` MCP tool

**Files:**
- Modify: `src/fantastical_mcp/server.py` (add the tool after the `get_events_by_calendar` tool, before `get_availability`)
- Test: `tests/integration/test_live.py` (one live end-to-end scoping test)

> **Note on testing:** the `@mcp.tool`-decorated function is not convenient to invoke directly in a unit test, and its body is thin glue over two already-tested pieces (`_resolve_range_window` from Task 1 and `db.get_events_in_range` from Task 2). It is verified by (a) the live integration test below exercising the exact resolve→scope flow on real data, and (b) a manual MCP smoke test (Step 5).

- [ ] **Step 1: Write the failing integration test**

In `tests/integration/test_live.py`, add this method inside the existing `TestLiveDatabase` class (it already has `self.db` from the autouse `setup_db` fixture):

```python
    def test_get_events_in_range_scopes_to_calendar(self):
        from datetime import datetime, timezone

        from fantastical_mcp.server import _resolve_range_window

        calendars = self.db.get_calendars()
        assert len(calendars) > 0
        name = calendars[0]["name"]

        window = _resolve_range_window(None, None, 30, datetime.now(timezone.utc))
        assert isinstance(window, tuple)
        start, end = window

        events = self.db.get_events_in_range(start, end, calendar_name=name)
        assert isinstance(events, list)
        # Scoping guarantee: every returned event belongs to the named calendar.
        for e in events:
            assert e["calendar"] == name
```

- [ ] **Step 2: Run the integration test to verify it fails**

Run: `pytest tests/integration/test_live.py::TestLiveDatabase::test_get_events_in_range_scopes_to_calendar -v -m integration`
Expected: FAIL — `ImportError: cannot import name '_resolve_range_window'` only if Task 1 was skipped; otherwise it passes already at the db layer. If it already passes, that is acceptable (Task 1 + Task 2 satisfy it) — proceed to add the tool so the public surface exists.

- [ ] **Step 3: Implement the tool**

In `src/fantastical_mcp/server.py`, add immediately after the `get_events_by_calendar` tool function and before `get_availability`. `format_events_by_date` is already imported.

```python
@mcp.tool
async def get_events_in_range(
    calendar: str | None = None,
    start: str | None = None,
    end: str | None = None,
    days_back: int | None = None,
) -> str:
    """Get events in an arbitrary date window (past or future), grouped by date.

    Specify the window in exactly ONE of two ways (not both):

    * Absolute: pass both `start` and `end` as "YYYY-MM-DD". `end` is
      inclusive of the whole day (e.g. start="2026-05-28", end="2026-06-10"
      covers all of the 10th).
    * Relative: pass `days_back` (a positive integer) for events from that
      many days ago through the end of today.

    Args:
        calendar: Optional calendar name to scope to (use get_calendars for
            names). Omit to query all calendars — note that an event mirrored
            across several calendars then appears once per calendar; scope to
            a single calendar to get a clean, duplicate-free list.
        start: Absolute-mode start date, "YYYY-MM-DD".
        end: Absolute-mode end date, "YYYY-MM-DD" (inclusive).
        days_back: Relative-mode window size in days.
    """
    now = datetime.now(timezone.utc)
    window = _resolve_range_window(start, end, days_back, now)
    if isinstance(window, str):
        return window
    win_start, win_end = window

    db = _get_db()
    events = db.get_events_in_range(win_start, win_end, calendar_name=calendar)
    if not events:
        scope = f"'{calendar}'" if calendar else "any calendar"
        where = (
            f"in the last {days_back} days"
            if days_back is not None
            else f"from {start} to {end}"
        )
        hint = (
            " (If unexpected, check the name with get_calendars.)"
            if calendar
            else ""
        )
        return f"No events in {scope} {where}.{hint}"
    return format_events_by_date(events)
```

- [ ] **Step 4: Run the integration test to verify it passes**

Run: `pytest tests/integration/test_live.py::TestLiveDatabase::test_get_events_in_range_scopes_to_calendar -v -m integration`
Expected: PASS (or SKIP if Fantastical is not installed on the runner).

- [ ] **Step 5: Manual MCP smoke test**

Reload the MCP server in your client and call the tool both ways against a known calendar, then confirm against Fantastical's UI:

```
get_events_in_range(calendar="Revl Coaching Shifts", start="2026-05-28", end="2026-06-10")
get_events_in_range(calendar="Revl Coaching Shifts", days_back=14)
get_events_in_range(start="2026-06-10", end="2026-05-28")   # expect the "before start" error
get_events_in_range(calendar="Revl Coaching Shifts", start="2026-05-28", end="2026-06-10", days_back=14)  # expect "not both"
```

Expected: the first two return day-grouped events scoped to the calendar with no cross-calendar duplicates; the last two return the clear error strings.

- [ ] **Step 6: Commit**

```bash
git add src/fantastical_mcp/server.py tests/integration/test_live.py
git commit -m "feat: add get_events_in_range MCP tool"
```

---

### Task 4: Documentation

**Files:**
- Modify: `docs/tools.md`, `README.md`, `CLAUDE.md`, `TODO.md`

- [ ] **Step 1: Add the tool to `docs/tools.md`**

Add a section (match the formatting of the neighbouring `get_events_by_calendar` entry):

```markdown
### get_events_in_range

Get events in an arbitrary date window (past or future), grouped by date,
optionally scoped to a single calendar.

Specify the window one of two ways (not both):

- **Absolute** — `start` and `end` as `YYYY-MM-DD`; `end` is inclusive of the whole day.
- **Relative** — `days_back` (positive int); from N days ago through the end of today.

**Parameters:**
- `calendar` (optional) — calendar name to scope to. Omit for all calendars. Scoping
  to one calendar removes cross-calendar mirrored copies; an all-calendar query returns
  one copy per calendar an event is mirrored onto.
- `start`, `end` (absolute mode) — `YYYY-MM-DD`.
- `days_back` (relative mode) — positive integer.

**Example:**

`get_events_in_range(calendar="Revl Coaching Shifts", start="2026-05-28", end="2026-06-10")`
```

- [ ] **Step 2: Update `README.md`**

Find the tool list / count in `README.md` and add `get_events_in_range` alongside `get_events_by_calendar`, updating any "N tools" count (12 → 13). Run `grep -n "get_events_by_calendar\|tools" README.md` to locate the spot.

- [ ] **Step 3: Update `CLAUDE.md`**

In the Architecture table, change the `server.py` row from "12 tool definitions" to "13 tool definitions".

- [ ] **Step 4: Update `TODO.md`**

Add under a dated heading:

```markdown
## get_events_in_range tool (Jun 8, 2026)
- [x] Add _resolve_range_window helper with absolute/relative modes + validation
- [x] Scope db.get_events_in_range to an optional named calendar
- [x] Add get_events_in_range MCP tool
- [x] Unit + integration tests
- [x] Docs (tools.md, README, CLAUDE.md)
```

- [ ] **Step 5: Run the full suite one last time**

Run: `pytest tests/ --ignore=tests/integration -v` (and `pytest -v` if Fantastical is available).
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add docs/tools.md README.md CLAUDE.md TODO.md
git commit -m "docs: document get_events_in_range tool"
```

---

## Self-Review

**Spec coverage:**
- Tool with absolute + relative mutually-exclusive modes → Task 1 (helper) + Task 3 (tool). ✓
- Inclusive `end` day → Task 1 (`end + 1 day`), asserted in `test_absolute_window_end_is_inclusive`. ✓
- All validation/error messages (both-modes, one-of-start/end, bad date, end<start, days_back≤0, range>MAX_DAYS, neither) → Task 1 tests. ✓
- Optional calendar scoping via backward-compatible `calendar_name` → Task 2. ✓
- Unknown calendar → `[]` → "no events" message → Task 2 test + Task 3 message. ✓
- Reuses `_collect_occurrences` clean path (no new phantom heuristics) → Task 2. ✓
- Output identical to siblings, no totals → Task 3 (`format_events_by_date`). ✓
- All-calendars returns raw (no cross-calendar dedup) → Task 2 `test_all_calendars_when_name_omitted`. ✓
- Tests (unit + integration) → Tasks 1–3. ✓
- Docs (tools.md, README, CLAUDE.md, TODO.md) → Task 4. ✓

**Placeholder scan:** none — all steps contain concrete code/commands.

**Type consistency:** `_resolve_range_window(start, end, days_back, now) -> tuple[datetime, datetime] | str` used identically in Tasks 1 and 3; `db.get_events_in_range(start, end, calendar_name=None)` defined in Task 2 and called with `calendar_name=` in Task 3 and the integration test. Tool name `get_events_in_range` consistent throughout.
