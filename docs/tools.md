# Tool Reference

fantastical-mcp exposes 15 tools via the Model Context Protocol. They are grouped into read tools (which query Fantastical's local database) and write tools (which use Fantastical's URL scheme). Three read tools (`get_today_json`, `get_upcoming_json`, `get_event_json`) return structured JSON rather than pretty-printed text, for programmatic clients.

---

## Read Tools

### `get_today`

Get all calendar events for today, grouped by calendar.

**Parameters:** None

**Example output:**

```
Today -- Monday 31 March 2026

Work
  09:00 -- 10:00  Team Standup @ Meeting Room A (id:42)
  14:00 -- 15:00  Sprint Review (recurring) (id:108)

Personal
  All day  Labour Day (id:86125)
```

---

### `get_upcoming`

Get events for the next N days, grouped by date.

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `days` | `int` | `7` | Number of days to look ahead |

**Example output:**

```
Monday 31 March 2026
  09:00 -- 10:00  Team Standup @ Meeting Room A (id:42)
  14:00 -- 15:00  Sprint Review (recurring) (id:108)

Tuesday 1 April 2026
  12:00 -- 13:00  Lunch with Sara @ The Crafers Hotel (id:101)
```

---

### `get_calendars`

List all calendars with their event counts. Excluded calendars (see [configuration](configuration.md)) are omitted.

**Parameters:** None

**Example output:**

```
Work (42 events)
Personal (18 events)
Family (7 events)
```

---

### `get_event`

Get full details for a specific event by its database ID.

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `event_id` | `int` | *required* | The event ID (shown in parentheses in event listings, e.g. `id:42`) |

**Example output:**

```
Team Standup
Calendar: Work
Date: Monday 31 March 2026
Time: 09:00 -- 10:00
Location: Meeting Room A
Organiser: Alice Smith <alice@example.com>
Attendees:
  - Alice Smith <alice@example.com>
  - Bob Jones <bob@example.com>
Notes: Bring laptop
Recurring: Yes
ID: 42 (id:42)
```

---

### `search_events`

Full-text search across event titles, locations, notes, and attendees. Uses SQLite FTS5 syntax.

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `query` | `str` | *required* | Search term. Supports FTS5 syntax: `AND`, `OR`, `NOT`, quotes for phrases. |
| `limit` | `int` | `20` | Maximum number of results |

**Example output:**

```
Monday 31 March 2026
  09:00 -- 10:00  Team Standup @ Meeting Room A (id:42)

Wednesday 26 March 2026
  09:00 -- 10:00  Team Standup @ Meeting Room A (recurring) (id:38)
```

Results are ordered by start date descending (most recent first).

---

### `get_events_by_calendar`

Get events from a specific calendar within a date window starting from today.

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `calendar` | `str` | *required* | Calendar name (e.g. `"Work"`, `"Personal"`). Use `get_calendars` to see available names. |
| `days` | `int` | `30` | Number of days to look ahead |

**Example output:**

```
Monday 31 March 2026
  09:00 -- 10:00  Team Standup @ Meeting Room A (id:42)
  14:00 -- 15:00  Sprint Review (recurring) (id:108)

Friday 4 April 2026
  10:00 -- 11:00  Performance Review (id:215)
```

---

### `get_availability`

Show free/busy time slots for a specific date. Calculates gaps between events within the 08:00--18:00 working window (local time). All-day events are listed separately.

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `date` | `str` | *required* | Date in `YYYY-MM-DD` format |
| `calendars` | `list[str]` | `None` (all calendars) | Optional list of calendar names to check |

**Example output:**

```
Availability for 2026-03-31

Free: 08:00 -- 09:00 (1h)
Busy: 09:00 -- 10:00  Team Standup (id:42)
Free: 10:00 -- 14:00 (4h)
Busy: 14:00 -- 15:00  Sprint Review (id:108)
Free: 15:00 -- 18:00 (3h)

All-day events:
  Labour Day (id:86125)
```

---

### `get_recurring`

List upcoming recurring events, optionally filtered by calendar. Useful for understanding the regular schedule (standups, focus blocks, coaching shifts, etc.).

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `calendar` | `str` | `None` (all calendars) | Optional calendar name to filter by. Use `get_calendars` to see available names. |
| `limit` | `int` | `50` | Maximum number of results |

**Example output:**

```
Work
  09:00 -- 10:00  Team Standup @ Meeting Room A (recurring) (id:42)
  14:00 -- 15:00  Sprint Review (recurring) (id:108)

Personal
  06:30 -- 07:30  Morning Yoga (recurring) (id:215)
```

Results are grouped by calendar and ordered by start date ascending. Only future instances are shown.

---

### `get_invitations`

List pending event invitations that need a response, ordered by start date (soonest first).

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `limit` | `int` | `20` | Maximum number of results |

**Example output:**

```
Wednesday 2 April 2026
  10:00 -- 11:00  Architecture Review @ Conference Room B (id:312)

Friday 4 April 2026
  15:00 -- 16:00  End of Quarter Drinks @ The Exeter (id:340)
```

---

### `get_recent`

Show the most recently added or synced calendar events. Useful for seeing what's new on the calendar without knowing specific dates.

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `limit` | `int` | `10` | Maximum number of results |

**Example output:**

```
Thursday 10 April 2026
  16:15 -- 18:45  Performance @ Glenelg (id:88958)

Monday 7 April 2026
  09:00 -- 10:00  Onboarding Kickoff (id:90650)
```

Results are ordered by recency (most recently added/synced first), not by event date.

---

## JSON Read Tools

These tools return structured Python dicts (serialised as JSON by MCP) rather than pretty-printed text. Use them from dashboards, automations, or any programmatic client that would otherwise need to parse the human-readable output. Event times are ISO-8601 strings.

### `get_today_json`

Machine-readable variant of `get_today`.

**Parameters:** None

**Response shape:**

```json
{
  "now": "2026-04-21T09:15:00+09:30",
  "timezone": "Australia/Adelaide",
  "events": [
    {
      "id": 42,
      "title": "Team Standup",
      "calendar": "Work",
      "start": "2026-04-21T09:00:00+00:00",
      "end": "2026-04-21T10:00:00+00:00",
      "all_day": false,
      "location": "Meeting Room A",
      "recurring": true,
      "attendees_count": 3
    }
  ]
}
```

---

### `get_upcoming_json`

Machine-readable variant of `get_upcoming`. Response mirrors `get_today_json` with an additional `days` field echoing the requested window.

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `days` | `int` | `7` | Number of days to look ahead (capped at 365) |

---

### `get_event_json`

Machine-readable variant of `get_event`. Returns the same summary fields as `get_today_json`, plus `notes`, `organizer`, and the full `attendees` list. Absent values are returned as `null` so the shape stays stable for callers. If the event id is not found, the response is `{"id": <id>, "found": false}`.

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `event_id` | `int` | *required* | The event rowid (as returned in the `id` field of `get_today_json` etc.) |

**Response shape (found):**

```json
{
  "found": true,
  "id": 42,
  "title": "Team Standup",
  "calendar": "Work",
  "start": "2026-04-21T09:00:00+00:00",
  "end": "2026-04-21T10:00:00+00:00",
  "all_day": false,
  "location": "Meeting Room A",
  "recurring": true,
  "attendees_count": 2,
  "notes": "Bring laptop",
  "organizer": {"displayName": "Alice Smith", "emailAddress": "alice@example.com"},
  "attendees": [
    {"displayName": "Alice Smith", "emailAddress": "alice@example.com"},
    {"displayName": "Bob Jones", "emailAddress": "bob@example.com"}
  ]
}
```

---

## Write Tools

### `create_event`

Create a new event in Fantastical using natural language. Fantastical's parser handles dates, times, locations, and recurrence naturally.

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `sentence` | `str` | *required* | Natural language event description, e.g. `"Lunch with Sara tomorrow at noon at The Crafers Hotel"` |
| `calendar` | `str` | `None` | Optional calendar name to create the event in |
| `add_immediately` | `bool` | `false` | If `true`, add without showing Fantastical's confirmation UI |

**Example output:**

```
Created event: Lunch with Sara tomorrow at noon at The Crafers Hotel (in Personal)
Fantastical is showing the event for confirmation.
```

**Notes:**

- When `add_immediately` is `false` (default), Fantastical opens and shows the parsed event for the user to confirm or edit before saving.
- Natural language examples: `"Weekly team standup every Monday at 9am"`, `"Dentist appointment next Thursday at 2:30pm for 45 minutes"`, `"Birthday party on 15 April from 6pm to 10pm at The Botanic Gardens"`.

---

### `show_date`

Open Fantastical's mini calendar to a specific date.

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `date` | `str` | *required* | Date in `YYYY-MM-DD` format |

**Example output:**

```
Opened Fantastical to 2026-04-15.
```
