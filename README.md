# Fantastical MCP

An MCP server that gives AI assistants read/write access to your Fantastical calendar on macOS.

## What it does

fantastical-mcp reads calendar events directly from Fantastical's local SQLite database and creates events via Fantastical's `x-fantastical3://` URL scheme. No TCC permissions, no API keys, no network access -- it works entirely offline using the data Fantastical already stores on your Mac.

- **Read** -- Query events by date range, calendar, or full-text search
- **Write** -- Create events using Fantastical's natural language parser
- **Navigate** -- Open Fantastical to a specific date

## Requirements

- macOS
- [Fantastical](https://flexibits.com/fantastical) installed with at least one calendar
- Python 3.12+

## Quick start

### Claude Desktop (1-click install)

1. Download `fantastical-mcp-0.1.0.mcpb` from the [latest release](https://github.com/jaydenk/fantastical-mcp/releases/latest)
2. Double-click the file
3. Done — Fantastical tools are now available in Claude Desktop

### Install from PyPI

```bash
uvx fantastical-mcp
```

### Local development

```bash
git clone https://github.com/jaydenk/fantastical-mcp.git
cd fantastical-mcp
uv venv && uv pip install -e ".[test]"
```

## Configuration

### Claude Code

Add to your `.claude/settings.json` (or project-level settings):

**Published package:**

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

**Local development:**

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

See [docs/configuration.md](docs/configuration.md) for environment variables, calendar exclusion, and transport options.

## Available tools

| Tool | Description |
|------|-------------|
| `get_today` | All events for today, grouped by calendar |
| `get_upcoming` | Events for the next N days, grouped by date |
| `get_calendars` | List all calendars with event counts |
| `get_event` | Full details for a specific event by ID |
| `search_events` | Full-text search across titles, locations, notes, attendees |
| `get_events_by_calendar` | Events from a specific calendar |
| `get_availability` | Free/busy time slots for a date |
| `get_recurring` | Upcoming recurring events, optionally filtered by calendar |
| `get_invitations` | Pending event invitations that need a response |
| `get_recent` | Most recently added or synced events |
| `create_event` | Create an event using natural language |
| `show_date` | Open Fantastical's mini calendar to a date |

See [docs/tools.md](docs/tools.md) for parameters, types, defaults, and example output.

## Limitations

- **No update or delete** -- Fantastical's URL scheme only supports event creation. Modification and deletion require EventKit, which needs TCC permissions.
- **macOS only** -- Relies on Fantastical's macOS database location and the `open` command.
- **Read-only database access** -- The database is opened in `?mode=ro` to prevent any risk of corruption.
- **Blob format dependency** -- The `NSKeyedArchiver` serialisation format is an internal detail of Fantastical and could change between versions. An FTS fallback path mitigates this.

## Documentation

- [Tool reference](docs/tools.md) -- Detailed parameters and example output for every tool
- [Configuration guide](docs/configuration.md) -- Environment variables, transport options, calendar exclusion
- [How it works](docs/how-it-works.md) -- Technical architecture and design decisions
- [Development guide](docs/development.md) -- Project structure, testing, and contributing

## Licence

[MIT](LICENSE)
