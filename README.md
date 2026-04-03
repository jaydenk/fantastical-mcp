# Fantastical MCP

[![Publish to PyPI](https://github.com/jaydenk/fantastical-mcp/actions/workflows/publish.yml/badge.svg)](https://github.com/jaydenk/fantastical-mcp/actions/workflows/publish.yml)

An MCP server that gives AI assistants read/write access to your Fantastical calendar on macOS.

## What it does

fantastical-mcp reads calendar events directly from Fantastical's local SQLite database and creates events via Fantastical's `x-fantastical3://` URL scheme. No TCC permissions, no API keys, no network access -- it works entirely offline using the data Fantastical already stores on your Mac.

- **Read** -- Query events by date range, calendar, or full-text search
- **Write** -- Create events using Fantastical's natural language parser
- **Navigate** -- Open Fantastical to a specific date

## Installation

### Prerequisites

- macOS
- [Fantastical](https://flexibits.com/fantastical) installed with at least one calendar
- An MCP client, such as Claude Desktop or Claude Code
- [uv](https://docs.astral.sh/uv/) Python package manager: `brew install uv`

### Install via uvx (Any MCP Client)

Fantastical MCP is published on PyPI and can be run directly with `uvx`:

```bash
uvx fantastical-mcp
```

Configure your MCP client to use `uvx` with `fantastical-mcp` as the argument.

### Claude Desktop

#### Option 1: One-Click Install (Recommended)

1. Download the latest `.mcpb` file from the [releases page](https://github.com/jaydenk/fantastical-mcp/releases/latest)
2. Double-click the file
3. Done!

#### Option 2: Manual Config

1. Go to **Claude → Settings → Developer → Edit Config**
2. Add the Fantastical server:

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

3. Save and restart Claude Desktop

### Claude Code

```bash
claude mcp add-json fantastical '{"command":"uvx","args":["fantastical-mcp"]}'
```

To make it available globally (across all projects), add `-s user`:

```bash
claude mcp add-json -s user fantastical '{"command":"uvx","args":["fantastical-mcp"]}'
```

### Verify it's working

After installation:
- If using Claude Desktop, you should see "Fantastical MCP" in the "Search and tools" list
- Try asking: "What's on my calendar today?"

### Sample Usage

- "What's on my calendar today?"
- "Do I have any meetings on Thursday?"
- "Create a lunch meeting with Sarah tomorrow at noon at The Italian Place"
- "When am I free this Wednesday afternoon?"
- "Show me all events from my Work calendar this week"
- "Do I have any pending event invitations?"

#### Tips

- Create a project in Claude with custom instructions that explain how you organise your calendars. Tell Claude which calendars to prioritise and how you like events formatted.
- Pair with a task management MCP server (like [things-mcp](https://github.com/hald/things-mcp)) so Claude can cross-reference your tasks and calendar, block time for deep work, or create todos from upcoming meetings.
- Use `get_availability` to quickly find free slots: "When am I free for a 90-minute block this week?"

### Local Development

```bash
git clone https://github.com/jaydenk/fantastical-mcp.git
cd fantastical-mcp
uv venv && uv pip install -e ".[test]"
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

## Troubleshooting

If it's not working:

1. **Make sure Fantastical is installed and has been opened at least once**
   - The Fantastical database needs to exist for the server to read events

2. **Claude Desktop can't find `uvx`**
   - Install uv globally with Homebrew (`brew install uv`)
   - **Alternative**: Use the full path to `uvx` in your config. Find it with `which uvx` (typically `/Users/USERNAME/.local/bin/uvx`)

3. **"Database not found" errors**
   - Fantastical stores its database at `~/Library/Group Containers/group.com.flexibits.fantastical2.mac/`. Ensure this path exists and is accessible.

4. **System calendars cluttering results**
   - Set `FANTASTICAL_EXCLUDED_CALENDARS` to hide calendars like Weather or Openings. See [docs/configuration.md](docs/configuration.md) for details.

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
