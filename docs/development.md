# Development Guide

## Project Structure

```
fantastical-mcp/
  src/fantastical_mcp/
    __init__.py          # Package entry point, exports `mcp`
    server.py            # FastMCP server definition and 12 tool handlers
    db.py                # SQLite database access layer (read-only)
    formatters.py        # Plain-text output formatters (Australian English)
    url_scheme.py        # URL scheme helpers for writes (x-fantastical3://)
  tests/
    __init__.py
    test_db.py           # Database layer unit tests (uses in-memory SQLite)
    test_formatters.py   # Formatter unit tests
    test_url_scheme.py   # URL scheme unit tests
    integration/
      __init__.py
      test_live.py       # Live database tests (require Fantastical installed)
  docs/                  # Detailed documentation
  pyproject.toml         # Build config (hatchling), dependencies, scripts
  env.example            # Example environment variables
  LICENSE                # MIT licence
  CLAUDE.md              # Claude Code working context
```

### Module responsibilities

| Module | Responsibility |
|--------|---------------|
| `server.py` | Defines the `FastMCP` instance, registers all 12 tools, initialises the database connection at import, handles transport configuration. Entry point via `main()`. |
| `db.py` | All SQLite interaction. Opens the database read-only, loads the calendar registry from blob data, decodes event blobs, provides query methods. Contains the three-tier read strategy and FTS fallback logic. |
| `formatters.py` | Converts event dicts into plain-text output. Groups events by date or calendar. Formats availability as free/busy blocks. All display text uses Australian English. |
| `url_scheme.py` | Builds `x-fantastical3://` URLs and executes them via `subprocess.run(["open", ...])`. |

---

## Setting Up the Dev Environment

```bash
# Clone and enter the project
git clone https://github.com/jaydenk/fantastical-mcp.git
cd fantastical-mcp

# Create a virtual environment and install with test dependencies
uv venv
uv pip install -e ".[test]"

# Activate the venv (for running commands directly)
source .venv/bin/activate
```

---

## Running Tests

### Unit tests

Unit tests use an in-memory SQLite database that mirrors Fantastical's schema. They do not require Fantastical to be installed.

```bash
pytest tests/ --ignore=tests/integration -v
```

### Integration tests

Integration tests connect to your real Fantastical database. They require Fantastical to be installed with at least one calendar containing data. Tests that cannot find the database are automatically skipped.

```bash
pytest tests/integration/ -v -m integration
```

### All tests

```bash
pytest -v
```

---

## How Blob Decoding Works

Each calendar event is stored as an `NSKeyedArchiver` binary plist blob. Decoding follows this pattern:

1. **Parse the plist** with `plistlib.loads(blob)`.
2. **Get the `$objects` array** -- this is the flat list of all archived objects.
3. **Get the root object** -- always at index 1 (the root dict is the first real object after `$null`).
4. **Resolve UID references** -- each field in the root dict points to another object in `$objects` via a UID. The `resolve_uid()` function handles three UID formats:
   - `plistlib.UID` (Python's native type)
   - `{"CF$UID": int}` (legacy cross-platform format)
   - Plain `int` (direct index)
5. **Convert dates** -- Date fields contain nested dicts with an `NS.time` key holding an NSDate timestamp (seconds since 2001-01-01 UTC).
6. **Resolve attendees** -- The `attendees` field points to an NSArray wrapper with an `NS.objects` key containing a list of UIDs, each pointing to an attendee dict with `displayName` and `emailAddress` fields.

If any step fails, `decode_event` returns `None` and the caller falls back to FTS + secondary index data.

---

## Adding New Tools

1. **Add the tool function** in `server.py`:
   ```python
   @mcp.tool
   async def my_new_tool(param: str) -> str:
       """Description shown to the AI assistant.

       Args:
           param: What this parameter does.
       """
       db = _get_db()
       # ... query logic ...
       return formatted_result
   ```

2. **Add any new database queries** in `db.py` as methods on `FantasticalDB`.

3. **Add any new formatters** in `formatters.py`. Follow the existing pattern of returning plain text with consistent formatting.

4. **Write tests**:
   - Unit tests in `tests/test_db.py` (for new DB methods) or a new test file.
   - Use the `test_db` and `populated_db` fixtures to work with seeded in-memory databases.

5. **Update documentation** in `docs/tools.md` with the new tool's parameters and example output.

---

## Known Quirks

### FTS5 partial matching

SQLite's FTS5 engine does not support bare `*` as a search term. Prefix matching requires at least one character before the asterisk (e.g. `meet*` matches "meeting", "meetings", "meetup"). A bare `*` query will raise a SQLite error.

### Blob format versioning

The `NSKeyedArchiver` blob format is an internal implementation detail of Fantastical. It could change between versions without notice. The FTS fallback path (`_decode_with_fts_fallback`) mitigates this: if a blob cannot be parsed, the server reconstructs a partial event from the FTS and secondary index tables, which use simpler, more stable schemas. The partial event will be missing attendees, organiser, and conference type data but will still have title, location, notes, dates, and calendar information.

### Calendar name resolution

Calendar names are loaded from blob data at startup and cached. If a new calendar is added while the server is running, the cache is refreshed on the next `calendar_name()` lookup that misses. Other query methods (e.g. `get_events_by_calendar`) may not see new calendars until the server is restarted.

### Hidden events

Some events in Fantastical's database are marked as `hidden` (e.g. declined invitations, cancelled occurrences). These are filtered out by all query methods via `AND (si.hidden IS NULL OR si.hidden = 0)`.

### Time zone handling

All timestamps are stored and queried in UTC. Conversion to local time happens only in the formatters, at display time. The availability tool anchors its 08:00--18:00 working window to the system's local timezone.
