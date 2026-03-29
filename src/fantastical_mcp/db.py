"""Database access layer for Fantastical's local SQLite store."""

from __future__ import annotations

import glob
import os
import plistlib
import sqlite3
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Seconds between the Unix epoch (1970-01-01) and the NSDate reference date
# (2001-01-01).  Used to convert NSDate timestamps to Unix timestamps.
NSDATE_OFFSET = 978307200

# Calendar names that are excluded from query results by default.  These are
# Fantastical system calendars that clutter normal usage.
DEFAULT_EXCLUDE_CALENDARS: set[str] = {
    "Weather",
    "Openings",
    "RSVP Invitations",
    "Proposals",
    "Notifications",
}

_DB_GLOB = os.path.expanduser(
    "~/Library/Group Containers/"
    "85C27NK92C.com.flexibits.fantastical2.mac/"
    "Database/Fantastical*.fcdata"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def find_database_path() -> str:
    """Auto-discover the Fantastical database file.

    Resolution order:
    1. ``FANTASTICAL_DB_PATH`` environment variable (must exist on disk).
    2. Glob match under the standard Fantastical group container.

    Returns the absolute path as a string.

    Raises:
        FileNotFoundError: If no database file can be located.
    """
    env_path = os.environ.get("FANTASTICAL_DB_PATH")
    if env_path:
        if not Path(env_path).exists():
            raise FileNotFoundError(
                f"FANTASTICAL_DB_PATH points to a file that does not exist: {env_path}"
            )
        return env_path

    matches = glob.glob(_DB_GLOB)
    if not matches:
        raise FileNotFoundError(
            "Could not find the Fantastical database.  Ensure Fantastical is "
            "installed, or set the FANTASTICAL_DB_PATH environment variable."
        )
    return matches[0]


def resolve_uid(
    objects: list,
    ref: plistlib.UID | dict | int | None,
) -> object | None:
    """Resolve an NSKeyedArchiver UID reference into the real object.

    Handles three representations that appear in practice:

    * ``plistlib.UID`` — Python's native keyed-archiver UID type.
    * ``dict`` with a ``CF$UID`` key — legacy / cross-platform representation.
    * ``int`` — plain integer index.

    Index 0 is the ``$null`` sentinel and always returns ``None``.
    """
    if ref is None:
        return None

    if isinstance(ref, plistlib.UID):
        idx = ref.data
    elif isinstance(ref, dict) and "CF$UID" in ref:
        idx = ref["CF$UID"]
    elif isinstance(ref, int):
        idx = ref
    else:
        return None

    if idx == 0:
        return None

    return objects[idx]


# ---------------------------------------------------------------------------
# Main database class
# ---------------------------------------------------------------------------


class FantasticalDB:
    """Read-only interface to Fantastical's local YapDatabase SQLite store.

    Parameters:
        db_path: Absolute path to the ``.fcdata`` file.
        exclude_calendars: Optional set of calendar *names* to hide from
            results.  When ``None``, falls back to the
            ``FANTASTICAL_EXCLUDE_CALENDARS`` environment variable (comma-
            separated) and then to :data:`DEFAULT_EXCLUDE_CALENDARS`.
    """

    def __init__(
        self,
        db_path: str,
        exclude_calendars: set[str] | None = None,
    ) -> None:
        uri = f"file:{db_path}?mode=ro"
        self._conn = sqlite3.connect(uri, uri=True)
        self._conn.row_factory = sqlite3.Row

        # Resolve the exclusion set.
        if exclude_calendars is not None:
            self._exclude: set[str] = exclude_calendars
        else:
            env = os.environ.get("FANTASTICAL_EXCLUDE_CALENDARS")
            if env:
                self._exclude = {s.strip() for s in env.split(",") if s.strip()}
            else:
                self._exclude = set(DEFAULT_EXCLUDE_CALENDARS)

        # Calendar registry: id → display name.
        self._cal_registry: dict[str, str] = {}
        self._load_calendars()

    # -- internal helpers ---------------------------------------------------

    def _load_calendars(self) -> None:
        """Read every ``calendars`` collection blob and populate the registry."""
        cur = self._conn.cursor()
        cur.execute(
            "SELECT key, data FROM database2 WHERE collection = 'calendars'"
        )
        for row in cur.fetchall():
            cal_id: str = row["key"]
            blob: bytes | None = row["data"]
            if blob is None:
                continue
            try:
                plist = plistlib.loads(blob)
                objects = plist.get("$objects", [])
                top = plist.get("$top", {})
                root_ref = top.get("root")
                root = resolve_uid(objects, root_ref)
                if not isinstance(root, dict):
                    continue
                title = resolve_uid(objects, root.get("title"))
                if isinstance(title, str):
                    self._cal_registry[cal_id] = title
            except Exception:  # noqa: BLE001
                # Skip corrupt or unreadable blobs.
                continue

    def _is_excluded(self, cal_id: str) -> bool:
        """Return ``True`` if the calendar should be hidden."""
        name = self._cal_registry.get(cal_id)
        if name is None:
            return False
        return name in self._exclude

    # -- public API ---------------------------------------------------------

    def calendar_name(self, cal_id: str) -> str | None:
        """Look up a calendar's display name by its identifier.

        If the identifier is not in the cache, the registry is reloaded once
        in case a new calendar was added since startup.
        """
        name = self._cal_registry.get(cal_id)
        if name is not None:
            return name
        # Refresh and try once more.
        self._load_calendars()
        return self._cal_registry.get(cal_id)

    def get_calendars(self) -> list[dict[str, str | int]]:
        """Return non-excluded calendars with event counts.

        Each dict contains:
        * ``id`` — the calendar identifier string.
        * ``name`` — the human-readable calendar name.
        * ``event_count`` — number of items in the secondary index.
        """
        # Count items per calendar from the secondary index.
        cur = self._conn.cursor()
        cur.execute(
            "SELECT calendarIdentifier, COUNT(*) AS cnt "
            "FROM secondaryIndex_index_calendarItems "
            "GROUP BY calendarIdentifier"
        )
        counts: dict[str, int] = {
            row["calendarIdentifier"]: row["cnt"] for row in cur.fetchall()
        }

        result: list[dict[str, str | int]] = []
        for cal_id, cal_name in self._cal_registry.items():
            if self._is_excluded(cal_id):
                continue
            result.append(
                {
                    "id": cal_id,
                    "name": cal_name,
                    "event_count": counts.get(cal_id, 0),
                }
            )
        return result

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()
