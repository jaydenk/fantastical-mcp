# CLAUDE.md

## Project Overview

**fantastical-mcp** is a Python MCP (Model Context Protocol) server that reads calendar events directly from Fantastical's local SQLite database and creates events via Fantastical's URL scheme.

## Architecture

- `src/fantastical_mcp/server.py` — FastMCP server entry point and tool definitions
- `src/fantastical_mcp/db.py` — SQLite database access layer for Fantastical's local store
- `src/fantastical_mcp/url_scheme.py` — URL scheme helpers for creating events
- `src/fantastical_mcp/formatters.py` — Output formatters for calendar data

## Design Document

The full design document and implementation plan lives in `~/Documents/Development/AGENT/` alongside the research workspace.

## Development

- Python >=3.12, managed with uv
- Install: `uv pip install -e ".[test]"`
- Run tests: `pytest`
- Integration tests (require Fantastical): `pytest -m integration`

## Conventions

- Use Australian English in all display text and documentation
- Follow the FastMCP patterns from the things-mcp reference implementation
- All timestamps stored in UTC, converted to local time only on display
- Environment variables documented in `env.example`
