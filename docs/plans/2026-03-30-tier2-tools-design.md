# Tier 2 Tools Design

**Date:** 2026-03-30
**Status:** Approved

## Overview

Add three new read-only tools to the MCP server: `get_recurring`, `get_invitations`, and `get_recent`. All follow the existing Approach A pattern — secondary index queries joined with `database2` for blob decoding, with FTS fallback.

## Tool Specifications

### get_recurring

**Purpose:** List recurring events to understand the regular schedule.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `calendar` | `str \| None` | `None` | Filter to a specific calendar |
| `limit` | `int` | `50` | Max results |

- **DB method:** `get_recurring_events(calendar_name=None, limit=50)`
- **Query:** `WHERE si.recurring = 1 AND si.startDate >= now`, exclude hidden + excluded calendars, `ORDER BY si.startDate ASC`
- **Output:** `format_events_by_calendar` — recurring events grouped by calendar

### get_invitations

**Purpose:** Show pending event invitations needing a response.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | `int` | `20` | Max results |

- **DB method:** `get_pending_invitations(limit=20)`
- **Query:** `WHERE si.invitationNeedsAction = 1`, exclude hidden + excluded calendars, `ORDER BY si.startDate ASC`
- **Output:** `format_events_by_date` — invitations grouped by date, soonest first

### get_recent

**Purpose:** Show recently added/synced events.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | `int` | `10` | Max results |

- **DB method:** `get_recent_events(limit=10)`
- **Query:** `ORDER BY d.rowid DESC`, exclude hidden + excluded calendars
- **Output:** `format_events_by_date` — recent events grouped by date

**Design note:** Uses `rowid DESC` rather than `startDate DESC`. Rowid ordering captures sync/creation order, which better matches "what's new on my calendar" than "furthest future event."

## Architecture

No new modules. Changes are scoped to:

- `db.py` — three new public methods following existing patterns
- `server.py` — three new `@mcp.tool` definitions
- `tests/test_db.py` — unit tests for each new DB method

No changes to `formatters.py` or `url_scheme.py` — existing formatters cover all output needs.
