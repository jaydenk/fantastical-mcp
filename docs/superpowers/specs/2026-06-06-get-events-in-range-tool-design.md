# Design — `get_events_in_range` look-back / date-range MCP tool

- **Date:** 2026-06-06
- **Status:** Approved (design); pending implementation plan
- **Branch:** `feat/get-events-in-range`
- **Component:** `fantastical-mcp`

## Problem

The existing read tools cannot answer "what events happened on calendar X between two
past dates?" cleanly:

- `get_events_by_calendar(calendar, days)` is calendar-scoped and clean, but the window
  is hardcoded to `[today, today + days]` — **forward only**. It cannot reach a fixed
  past window, nor a window that ends in the future (e.g. a pay cycle running
  28 May → 10 Jun while today is 6 Jun).
- `search_events(query, limit)` can reach the past, but it is **FTS-based, spans every
  calendar, and applies no calendar scoping or cross-calendar dedup**. The same logical
  event mirrored across several subscribed calendars is returned 2–4×, and results
  depend on the title matching the query.

### Root-cause discovery (motivating this tool)

Investigated while tallying "Revl Coaching Shifts" hours. The apparent "duplicate"
events were **cross-calendar mirroring**: the same shift exists on three calendars —
`Revl Coaching Shifts` (locally authored, `href = NULL` in
`secondaryIndex_index_calendarItems`), `Mela`, and `Jayden Work` (both CalDAV-synced,
non-NULL `href`). `search_events` returns all three copies because it does not scope by
calendar.

Critically, the **locally-authored calendar reflects the user's edits/removals** (e.g.
cancelled Friday-morning shifts), while the synced feeds retain stale pre-removal copies.
No status column distinguishes a removed-but-lingering event — `syncStatus`, `hidden`,
`hasMovedToIdentifier`, and `resolvedEventIdentifier` are **identical** between a real
shift and a stale one. Therefore **no deletion-detection heuristic is needed or possible**;
**scoping the query to the single source-of-truth calendar is the entire fix.** When scoped
to one calendar, the raw secondary-index rows and the clean `_collect_occurrences` path
return identical, duplicate-free results.

## Goal

Add one MCP tool that returns the clean, calendar-scoped events in an arbitrary date
window (past or future), reusing the existing clean query engine.

### Non-goals (explicitly out of scope)

- **No aggregation.** No hours totals, shift counts, or summaries — the tool returns
  clean events; any calculation is the caller's job. (User decision.)
- **No cross-calendar dedup** in the all-calendars case. Omitting `calendar` returns all
  non-excluded calendars raw (mirrored copies included); scoping to a calendar is the
  documented way to get a clean list. (User decision.)
- **No forward-only convenience mode** — `get_upcoming` / `get_events_by_calendar`
  already cover "next N days".
- **No deletion/phantom heuristics** — proven unnecessary (see root-cause above).

## Design

### New tool — `get_events_in_range` (`server.py`)

Tool count 12 → 13.

```python
@mcp.tool
async def get_events_in_range(
    calendar: str | None = None,   # scope to one calendar by name; omit = all non-excluded (raw, may mirror)
    start: str | None = None,      # absolute mode: "YYYY-MM-DD"
    end: str | None = None,        # absolute mode: "YYYY-MM-DD", INCLUSIVE of the whole day
    days_back: int | None = None,  # relative mode: last N days through end of today
) -> str
```

Two **mutually-exclusive** modes, never inferred ambiguously. The docstring states
explicitly which arguments select absolute vs relative.

**Absolute mode** — `start` *and* `end` supplied (`YYYY-MM-DD`):
- `window_start` = local midnight of `start`.
- `window_end` = local midnight of `(end + 1 day)`, so `end` is **inclusive** of the
  whole day (28 May → 10 Jun captures all of the 10th).

**Relative mode** — `days_back` supplied (positive int):
- `window_start` = local midnight of `(today − days_back)`.
- `window_end` = local midnight of `(today + 1 day)` (through the end of today).
- Documented meaning: "events from N days ago through the end of today."

Both windows are computed in the **local timezone** then converted to UTC for the query,
matching the existing `get_availability` / `get_upcoming` idiom.

### Validation (clear errors, no silent guessing)

Resolved in a **pure helper** `_resolve_range_window(start, end, days_back, now) ->
tuple[datetime, datetime] | str` (returns a UTC `(start, end)` window, or an error string).
Extracting this keeps it unit-testable without a live database. Rules, in order:

| Condition | Result |
|-----------|--------|
| absolute arg(s) **and** `days_back` both present | error: *"Use either absolute dates (start, end) or a relative window (days_back), not both."* |
| exactly one of `start`/`end` present | error: *"Absolute mode needs both start and end in YYYY-MM-DD format."* |
| `start`/`end` fail to parse | error: *"Invalid date format: {bad}. Use YYYY-MM-DD."* |
| `end` earlier than `start` | error: *"end ({end}) is before start ({start})."* |
| `days_back` ≤ 0 | error: *"days_back must be a positive integer."* |
| resolved window spans > `MAX_DAYS` (365) | error: *"Range too large (max {MAX_DAYS} days)."* |
| neither mode supplied | usage: *"Specify either absolute dates (start and end, YYYY-MM-DD) or a relative window (days_back)."* |

### Engine change — `db.get_events_in_range` (`db.py`)

Add an optional, backward-compatible parameter:

```python
def get_events_in_range(self, start, end, calendar_name=None):
    calendar_ids = None
    if calendar_name is not None:
        calendar_ids = [cid for cid, n in self._cal_registry.items() if n == calendar_name]
        if not calendar_ids:
            return []          # unknown calendar → no events
    return self._collect_occurrences(start, end, calendar_ids=calendar_ids)
```

- Default `calendar_name=None` ⇒ `calendar_ids=None` ⇒ all non-excluded calendars —
  **identical to current behaviour**, so every existing caller (`get_today`,
  `get_upcoming`, `get_availability`, JSON variants) is unaffected.
- `_collect_occurrences` is the clean path: `hidden` filter, recurring expansion,
  detached-instance dedup, exclusion set honoured. No new query logic is introduced.

### Data flow

```
tool(get_events_in_range)
  → _resolve_range_window(...)          # parse + validate → UTC (start, end) | error str
  → db.get_events_in_range(s, e, calendar_name=calendar)
      → resolve name to calendar_ids
      → _collect_occurrences(s, e, calendar_ids)   # existing clean engine
  → format_events_by_date(events)       # existing formatter, identical to siblings
```

### Output

- Events present → `format_events_by_date(events)` (day-grouped, same as `get_upcoming`
  / `get_events_by_calendar`). **No footer, no totals.**
- No events → a clear message naming the scope and window, e.g.
  *"No events in 'Revl Coaching Shifts' from 2026-05-28 to 2026-06-10."* (absolute) or
  *"No events in 'Revl Coaching Shifts' in the last 14 days."* (relative). When a
  calendar was named, append a hint: *"(If unexpected, check the name with get_calendars.)"*
  This avoids a separate not-found code path and sidesteps the excluded-calendar edge case.

## Edge cases

- **Unknown calendar name** → `db` returns `[]` → "no events" message with the
  `get_calendars` hint (not a hard error; keeps one code path).
- **Excluded calendar named explicitly** (e.g. "Weather") → returns `[]`; acceptable
  (those are system calendars, out of scope).
- **Single day** → `start == end` is valid (inclusive end → one full day window).
- **All-day events** in the window → returned as-is by the formatter (no duration math
  attempted, consistent with non-goal).
- **Recurring series** spanning the window → expanded per-occurrence by the existing
  engine; no change.

## Testing

**Unit (`tests/`, no Fantastical required)** — target `_resolve_range_window`:
- absolute both → correct UTC window, end-day inclusive (assert `window_end` is midnight
  after `end`).
- relative `days_back` → correct window relative to an injected `now`.
- both modes supplied → error string.
- only `start` (or only `end`) → error.
- malformed date → error.
- `end` < `start` → error.
- `days_back` ≤ 0 → error.
- window > `MAX_DAYS` → error.
- neither supplied → usage string.

**Integration (`tests/integration/`, marked `@integration`, requires Fantastical):**
- `db.get_events_in_range(s, e, calendar_name=X)` returns only events whose `calendar == X`.
- The same window via the new tool returns a count ≤ the unscoped `search_events` count
  for the same titles (demonstrates cross-calendar mirroring is collapsed by scoping).

## Documentation to update (in the implementation PR)

- `docs/tools.md` — new tool entry with both modes and examples.
- `README.md` — tool count / list.
- `CLAUDE.md` — "12 tool definitions" → 13.
- `TODO.md` — note the addition.

## Future (not now)

- Optional cross-calendar dedup for the all-calendars case (decided against for YAGNI).
- A `days_forward` symmetric option (currently covered by `get_upcoming`).
