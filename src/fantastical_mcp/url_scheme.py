"""URL scheme helpers for creating events and navigating Fantastical."""

import subprocess
import urllib.parse


def create_event_url(
    sentence: str,
    calendar: str | None = None,
    add_immediately: bool = False,
) -> str:
    """Build a Fantastical URL for creating an event via natural language."""
    params = {"s": sentence}
    if calendar:
        params["calendarName"] = calendar
    if add_immediately:
        params["add"] = "1"
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"x-fantastical3://parse?{query}"


def show_date_url(date_str: str) -> str:
    """Build a Fantastical URL to open the mini calendar to a specific date (YYYY-MM-DD)."""
    return f"x-fantastical3://show/mini/{date_str}"


def execute_url(url: str, background: bool = True) -> None:
    """Execute a Fantastical URL scheme command via macOS open."""
    cmd = ["open"]
    if background:
        cmd.append("-g")
    cmd.append(url)
    subprocess.run(cmd, check=True, capture_output=True, text=True)
