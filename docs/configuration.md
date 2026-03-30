# Configuration Guide

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FANTASTICAL_DB_PATH` | Auto-detected | Override the auto-discovered database path. Must point to an existing `.fcdata` file. |
| `FANTASTICAL_EXCLUDE_CALENDARS` | `Weather,Openings,RSVP Invitations,Proposals,Notifications` | Comma-separated calendar names to hide from all query results. Replaces the default exclusion list entirely when set. |
| `FANTASTICAL_MCP_TRANSPORT` | `stdio` | Transport mode: `stdio` (default for CLI tools) or `sse` (HTTP server). |
| `FANTASTICAL_MCP_HOST` | `127.0.0.1` | Host address for SSE transport. |
| `FANTASTICAL_MCP_PORT` | `8000` | Port for SSE transport. |

An example `.env` file is provided as `env.example` in the project root.

---

## Claude Code

### Published package

Add to `.claude/settings.json` (user-level) or `.claude/settings.local.json` (project-level):

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

### Local development

Use `uv run --directory` to point at the cloned repository:

```json
{
  "mcpServers": {
    "fantastical": {
      "command": "uv",
      "args": ["run", "--directory", "/Users/you/path/to/fantastical-mcp", "fantastical-mcp"]
    }
  }
}
```

### With environment variables

```json
{
  "mcpServers": {
    "fantastical": {
      "command": "uv",
      "args": ["run", "--directory", "/Users/you/path/to/fantastical-mcp", "fantastical-mcp"],
      "env": {
        "FANTASTICAL_EXCLUDE_CALENDARS": "Weather,Openings,RSVP Invitations"
      }
    }
  }
}
```

---

## Claude Desktop

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

For local development:

```json
{
  "mcpServers": {
    "fantastical": {
      "command": "uv",
      "args": ["run", "--directory", "/Users/you/path/to/fantastical-mcp", "fantastical-mcp"]
    }
  }
}
```

---

## Calendar Exclusion

By default, several Fantastical system calendars are hidden from results:

- Weather
- Openings
- RSVP Invitations
- Proposals
- Notifications

### Override via environment variable

Setting `FANTASTICAL_EXCLUDE_CALENDARS` **replaces** the default list entirely. To exclude only Weather and Proposals:

```bash
FANTASTICAL_EXCLUDE_CALENDARS="Weather,Proposals"
```

To exclude nothing (show all calendars):

```bash
FANTASTICAL_EXCLUDE_CALENDARS=""
```

### Override via constructor

When using `FantasticalDB` directly (e.g. in tests), pass `exclude_calendars`:

```python
db = FantasticalDB(db_path, exclude_calendars={"Weather"})
```

Priority order:
1. `exclude_calendars` constructor parameter (highest)
2. `FANTASTICAL_EXCLUDE_CALENDARS` environment variable
3. Built-in default set (lowest)

---

## Transport Options

### stdio (default)

Used by Claude Code and Claude Desktop. The MCP client spawns the server as a subprocess and communicates over stdin/stdout. No configuration needed beyond the MCP server entry.

### SSE (Server-Sent Events)

For use cases where the server runs as a persistent HTTP process:

```bash
FANTASTICAL_MCP_TRANSPORT=sse FANTASTICAL_MCP_HOST=127.0.0.1 FANTASTICAL_MCP_PORT=8000 fantastical-mcp
```

The server will listen on `http://127.0.0.1:8000` and serve the MCP protocol over SSE. This is useful for development, debugging, or connecting from MCP clients that support HTTP transport.
