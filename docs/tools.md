# Tool Reference

fantastical-mcp exposes 9 tools via the Model Context Protocol. They are grouped into read tools (which query Fantastical's local database) and write tools (which use Fantastical's URL scheme).

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
