# How It Works

This document explains the technical architecture of fantastical-mcp: how it reads from Fantastical's database, how it writes events, and why this approach was chosen.

## Why not EventKit or AppleScript?

Most calendar integrations on macOS use one of two approaches:

| Approach | Pros | Cons |
|----------|------|------|
| **EventKit** (native framework) | Full CRUD, system calendar access | Requires TCC permissions (user must grant calendar access in System Settings). MCP servers run as subprocesses, making TCC prompts unreliable. |
| **AppleScript** | Scriptable, works with Calendar.app | Fantastical's AppleScript support is limited. Requires Automation permissions (another TCC prompt). |
| **Direct database read** | No permissions needed, offline, fast | Read-only, format may change between versions |

fantastical-mcp takes the direct database approach. Since Fantastical stores its data in `~/Library/Group Containers/` (which is readable without TCC permissions), and we only need read-only access for queries, this avoids all permission issues. Writes are handled via the URL scheme, which delegates to Fantastical itself.

---

## Fantastical's Database

Fantastical uses [YapDatabase](https://github.com/yapstudios/YapDatabase), a key-value/collection store built on top of SQLite. The database file is located at:

```
~/Library/Group Containers/85C27NK92C.com.flexibits.fantastical2.mac/Database/Fantastical*.fcdata
```

The `.fcdata` file is a standard SQLite database. The server opens it in read-only mode (`?mode=ro`) to eliminate any risk of corruption.

### Key tables

| Table | Purpose |
|-------|---------|
| `database2` | Main YapDatabase store. Each row has a `collection`, `key`, and `data` (binary blob). Calendar items live in collections named `calendarItems-{calendarId}`. Calendar metadata lives in the `calendars` collection. |
| `secondaryIndex_index_calendarItems` | Pre-extracted fields from event blobs: `startDate`, `calendarIdentifier`, `hidden`, `isAllDayOrFloating`, `recurring`, etc. Enables fast SQL queries without blob decoding. |
| `fts_fts` | FTS5 virtual table indexing event titles, locations, notes, URLs, attendees, and attachments. Powers full-text search. |

---

## The Three-Tier Read Strategy

Depending on the query type, fantastical-mcp uses one of three data access tiers:

### Tier 1: Secondary index

Used for date-range filtering (`get_today`, `get_upcoming`, `get_events_in_range`) and calendar lookups (`get_events_by_calendar`). The `secondaryIndex_index_calendarItems` table stores pre-extracted fields, so queries can filter by `startDate`, `calendarIdentifier`, and `hidden` without touching the blob data.

```sql
SELECT d.rowid, d.data, si.calendarIdentifier
FROM database2 d
JOIN secondaryIndex_index_calendarItems si ON d.rowid = si.rowid
WHERE si.startDate >= ? AND si.startDate < ?
AND (si.hidden IS NULL OR si.hidden = 0)
ORDER BY si.startDate ASC
```

The blob is still decoded for the full event details (title, attendees, etc.), but the secondary index handles the heavy filtering.

### Tier 2: FTS5 virtual table

Used for `search_events`. The `fts_fts` table provides full-text search across titles, locations, notes, and attendees using SQLite's FTS5 engine.

```sql
SELECT d.rowid, d.data, si.calendarIdentifier, si.startDate
FROM fts_fts f
JOIN database2 d ON d.rowid = f.rowid
JOIN secondaryIndex_index_calendarItems si ON si.rowid = f.rowid
WHERE fts_fts MATCH ?
AND (si.hidden IS NULL OR si.hidden = 0)
ORDER BY si.startDate DESC
LIMIT ?
```

FTS5 supports `AND`, `OR`, `NOT`, phrase matching (with quotes), and prefix matching (with `*`). Note that bare `*` is not valid -- it must follow a term (e.g. `meet*`).

### Tier 3: Blob decode

Every event's full details are stored as an `NSKeyedArchiver` binary plist blob in the `database2.data` column. The `decode_event` method parses this blob to extract:

- Title, location, notes
- Start and end dates
- Calendar identifier
- All-day flag
- Attendees (name and email)
- Organiser (name and email)
- Recurrence presence
- Conference type

If blob decoding fails (e.g. due to a format change in a newer Fantastical version), a **fallback path** combines data from the FTS table (title, location, notes) and the secondary index (dates, calendar, flags) to construct a partial event. This ensures the server degrades gracefully rather than failing entirely.

---

## NSKeyedArchiver and Blob Format

### What is NSKeyedArchiver?

`NSKeyedArchiver` is Apple's serialisation format for Objective-C and Swift objects. It stores objects as binary property lists (plists) with a specific structure:

- `$archiver`: Always `"NSKeyedArchiver"`
- `$version`: Archive format version
- `$top`: Dictionary mapping logical names to UID references
- `$objects`: Array of all archived objects, referenced by index (UID)

### UID resolution pattern

Objects in the `$objects` array reference each other via UIDs -- integer indices into the array. Index 0 is always the `$null` sentinel. The `resolve_uid` function handles three UID representations that appear in practice:

1. `plistlib.UID` -- Python's native keyed-archiver UID type
2. `dict` with a `CF$UID` key -- legacy/cross-platform representation
3. Plain `int` -- direct integer index

### NSDate epoch conversion

Apple's `NSDate` stores timestamps as seconds since **1 January 2001 00:00:00 UTC** (the "Apple epoch"), not the Unix epoch (1 January 1970). The offset between the two is 978,307,200 seconds:

```python
NSDATE_OFFSET = 978307200  # seconds between Unix epoch and NSDate epoch

def nsdate_to_datetime(nsdate: float) -> datetime:
    return datetime.fromtimestamp(nsdate + NSDATE_OFFSET, tz=timezone.utc)
```

All dates in the secondary index table use NSDate timestamps. The server converts these to UTC `datetime` objects on read, and converts back to local time only when formatting display output.

---

## URL Scheme for Writes

Fantastical supports event creation via its `x-fantastical3://` URL scheme. The server constructs a URL and opens it via the macOS `open` command:

```
x-fantastical3://parse?s=Lunch+with+Sara+tomorrow+at+noon&calendarName=Personal
```

**Parameters:**

| URL parameter | Description |
|---------------|-------------|
| `s` | Natural language event description (passed to Fantastical's parser) |
| `calendarName` | Optional target calendar name |
| `add` | If `1`, add immediately without showing the confirmation UI |

The `open` command is called with the `-g` flag (open in background) for event creation, so the user's current app stays in focus. For `show_date`, the `-g` flag is omitted so Fantastical comes to the foreground.

### Why URL scheme instead of direct database writes?

1. **Safety** -- Writing to YapDatabase requires understanding its internal journaling, metadata, and index update logic. A malformed write could corrupt the database.
2. **Validation** -- Fantastical's parser handles complex natural language, recurrence rules, and calendar-specific logic that would be extremely difficult to replicate.
3. **User control** -- With `add_immediately=false` (the default), the user sees the parsed event and can confirm, edit, or cancel before it is saved.

---

## Database Discovery

The server auto-discovers the database file by globbing:

```
~/Library/Group Containers/85C27NK92C.com.flexibits.fantastical2.mac/Database/Fantastical*.fcdata
```

This path is stable across Fantastical versions. The `FANTASTICAL_DB_PATH` environment variable can override auto-discovery for non-standard installations or testing.

Resolution order:
1. `FANTASTICAL_DB_PATH` environment variable (must exist on disk)
2. Glob match under the standard Fantastical group container
3. Raise `FileNotFoundError` if neither succeeds
