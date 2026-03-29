# fantastical-mcp

Fantastical calendar MCP server — read events from Fantastical's local database, create via URL scheme.

Full documentation coming soon.

## Testing

```bash
# Install with test dependencies
uv pip install -e ".[test]"

# Run unit tests
pytest tests/ --ignore=tests/integration -v

# Run integration tests (requires Fantastical installed with calendar data)
pytest tests/integration/ -v -m integration
```

Integration tests are automatically skipped if Fantastical is not installed on the machine.
