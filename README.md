# Fantastical MCP Server

An MCP (Model Context Protocol) server that gives AI assistants read/write access to your Fantastical calendar on macOS.

## What It Does

fantastical-mcp reads calendar events directly from Fantastical's local SQLite database and creates events via Fantastical's `x-fantastical3://` URL scheme. This approach requires no TCC permissions, no API keys, and no network access -- it works entirely offline using the data Fantastical already stores on your Mac.

- **Read** — Query events by date range, calendar, or full-text search
- **Write** — Create events using Fantastical's natural language parser
- **Navigate** — Open Fantastical to a specific date

## Requirements

- macOS (Fantastical stores its database in `~/Library/Group Containers/`)
- [Fantastical](https://flexibits.com/fantastical) installed with at least one calendar
- Python 3.12+

## Installation

### Published package (once on PyPI)

```bash
uvx fantastical-mcp
```

### Local development

```bash
git clone https://github.com/jaydenk/fantastical-mcp.git
cd fantastical-mcp
uv venv
uv pip install -e ".[test]"
```

## Configuration

### Claude Code

Add to your Claude Code MCP settings (`.claude/settings.json` or project-level):

**Using published package:**

```json
{
  "mcpServers": {
    "fantastical": {
      "command": "uvx",
      "args": ["fantastical-mcp"]
    }
  }
}
```

**Using local development install:**

```json
{
  "mcpServers": {
    "fantastical": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/fantastical-mcp", "fantastical-mcp"]
    }
  }
}
```

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "fantastical": {
      "command": "uvx",
      "args": ["fantastical-mcp"]
    }
  }
}
```

## Available Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_today` | Get all events for today, grouped by calendar | — |
| `get_upcoming` | Get events for the next N days, grouped by date | `days` (default: 7) |
| `get_calendars` | List all calendars with event counts | — |
| `get_event` | Get full details for a specific event | `event_id` |
| `search_events` | Full-text search across titles, locations, notes, attendees | `query`, `limit` (default: 20) |
| `get_events_by_calendar` | Get events from a specific calendar | `calendar`, `days` (default: 30) |
| `get_availability` | Show free/busy time slots for a date | `date` (YYYY-MM-DD), `calendars` (optional list) |
| `create_event` | Create an event using natural language | `sentence`, `calendar` (optional), `add_immediately` (default: false) |
| `show_date` | Open Fantastical's mini calendar to a date | `date` (YYYY-MM-DD) |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FANTASTICAL_DB_PATH` | Override auto-discovered database path | Auto-detected |
| `FANTASTICAL_EXCLUDE_CALENDARS` | Comma-separated calendar names to hide | `Weather,Openings,RSVP Invitations,Proposals,Notifications` |
| `FANTASTICAL_MCP_TRANSPORT` | Transport mode (`stdio` or `sse`) | `stdio` |
| `FANTASTICAL_MCP_HOST` | Host for SSE transport | `127.0.0.1` |
| `FANTASTICAL_MCP_PORT` | Port for SSE transport | `8000` |

## How It Works

Fantastical uses a [YapDatabase](https://github.com/yapstudios/YapDatabase) SQLite store. Each calendar event is serialised as an `NSKeyedArchiver` binary plist blob in the `database2` table. The server uses a three-tier read strategy:

1. **Secondary index** (`secondaryIndex_index_calendarItems`) — Used for date-range filtering and calendar lookups. This table stores pre-extracted fields like `startDate`, `calendarIdentifier`, and `hidden`, enabling fast SQL queries without blob decoding.
2. **FTS5 virtual table** (`fts_fts`) — Powers full-text search across event titles, locations, notes, and attendees.
3. **Blob decode** — `NSKeyedArchiver` plists are decoded with Python's `plistlib` to extract full event details (attendees, organiser, recurrence, conference type). Falls back to FTS + secondary index data if a blob cannot be parsed.

For writes, the server constructs `x-fantastical3://parse?` URLs and opens them via `macOS open`, which hands the natural language string to Fantastical's parser.

## Limitations

- **No update or delete** — Fantastical's URL scheme only supports event creation. Modification and deletion require EventKit, which needs TCC permissions.
- **Blob format dependency** — The `NSKeyedArchiver` serialisation format is an internal implementation detail of Fantastical and could change between versions. The FTS fallback path mitigates this.
- **macOS only** — Relies on Fantastical's macOS database location and the `open` command.
- **Read-only database access** — The database is opened in `?mode=ro` to avoid any risk of corruption.

## Development

### Project structure

```
src/fantastical_mcp/
    __init__.py        # Package entry, exports `mcp`
    server.py          # FastMCP server and tool definitions
    db.py              # SQLite database access layer
    formatters.py      # Plain-text output formatters
    url_scheme.py      # URL scheme helpers for writes
tests/
    test_db.py         # Database layer unit tests
    test_formatters.py # Formatter unit tests
    test_url_scheme.py # URL scheme unit tests
    integration/       # Live database tests (require Fantastical)
```

### Running tests

```bash
# Unit tests (no Fantastical required)
pytest tests/ --ignore=tests/integration -v

# Integration tests (requires Fantastical installed with calendar data)
pytest tests/integration/ -v -m integration
```

### Setting up for development

```bash
uv venv
uv pip install -e ".[test]"
```

## Licence

[MIT](LICENSE)
