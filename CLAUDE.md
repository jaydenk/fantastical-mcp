# CLAUDE.md

## Project Overview

**fantastical-mcp** is a Python MCP (Model Context Protocol) server that gives AI assistants read/write access to the Fantastical calendar on macOS. It reads events directly from Fantastical's local SQLite database and creates events via Fantastical's `x-fantastical3://` URL scheme. No TCC permissions or API keys are needed.

## Architecture

| Module | Responsibility |
|--------|---------------|
| `src/fantastical_mcp/server.py` | FastMCP server entry point, 12 tool definitions, transport config |
| `src/fantastical_mcp/db.py` | Read-only SQLite access to Fantastical's YapDatabase store. Three-tier read strategy: secondary index, FTS5, blob decode with FTS fallback. |
| `src/fantastical_mcp/formatters.py` | Plain-text output formatters. Australian English throughout. UTC to local time conversion on display. |
| `src/fantastical_mcp/url_scheme.py` | URL scheme helpers for event creation and date navigation |

## Documentation

- `docs/tools.md` -- Detailed tool reference with parameters and example output
- `docs/configuration.md` -- Environment variables, Claude Code/Desktop config, calendar exclusion
- `docs/how-it-works.md` -- Technical architecture: YapDatabase, NSKeyedArchiver, NSDate epoch, URL scheme, TCC avoidance
- `docs/development.md` -- Project structure, testing, blob decoding, adding tools, known quirks

## Development

- Python >=3.12, managed with `uv`
- Install: `uv pip install -e ".[test]"`
- Activate venv: `source .venv/bin/activate`
- Unit tests (no Fantastical required): `pytest tests/ --ignore=tests/integration -v`
- Integration tests (require Fantastical): `pytest tests/integration/ -v -m integration`
- All tests: `pytest -v`

## Conventions

- **Australian English** in all display text and documentation (Licence, Organiser, serialisation, etc.)
- All timestamps stored in UTC, converted to local time only on display
- Database opened read-only (`?mode=ro`) to prevent corruption
- Environment variables documented in `env.example`
- Follow the FastMCP patterns for tool definitions

## Key Design Decisions

- Direct database read avoids TCC permission issues that plague EventKit and AppleScript approaches
- FTS fallback path ensures graceful degradation if `NSKeyedArchiver` blob format changes
- Writes use URL scheme to delegate parsing, validation, and persistence to Fantastical itself
- Default calendar exclusions hide system calendars (Weather, Openings, etc.) from cluttering results
