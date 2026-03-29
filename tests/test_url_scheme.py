from unittest.mock import patch
from fantastical_mcp.url_scheme import create_event_url, show_date_url, execute_url


class TestCreateEventUrl:
    def test_basic_event(self):
        url = create_event_url("Lunch with Sara tomorrow at noon")
        assert url.startswith("x-fantastical3://parse?")
        assert "s=Lunch" in url

    def test_with_calendar(self):
        url = create_event_url("Meeting at 3pm", calendar="Work")
        assert "calendarName=Work" in url

    def test_add_immediately(self):
        url = create_event_url("Quick event", add_immediately=True)
        assert "add=1" in url

    def test_not_add_immediately(self):
        url = create_event_url("Quick event", add_immediately=False)
        assert "add=1" not in url

    def test_special_characters_encoded(self):
        url = create_event_url("Meeting & Discussion @ 3pm")
        # Ampersand should be encoded
        assert "%26" in url or "s=Meeting" in url


class TestShowDateUrl:
    def test_iso_date(self):
        url = show_date_url("2026-04-15")
        assert url == "x-fantastical3://show/mini/2026-04-15"

    def test_different_date(self):
        url = show_date_url("2026-12-25")
        assert "2026-12-25" in url


class TestExecuteUrl:
    @patch("fantastical_mcp.url_scheme.subprocess.run")
    def test_calls_open_with_background_flag(self, mock_run):
        execute_url("x-fantastical3://parse?s=test")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "open" in args
        assert "-g" in args
        assert "x-fantastical3://parse?s=test" in args

    @patch("fantastical_mcp.url_scheme.subprocess.run")
    def test_show_date_no_background_flag(self, mock_run):
        execute_url("x-fantastical3://show/mini/2026-04-15", background=False)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "open" in args
        assert "-g" not in args
