# FastMCP Datetime Server

## Summary
Implement a standalone FastMCP server (`mcp/datetime_server.py`) that exposes a `normalize_date` tool over stdio transport, independently runnable and testable before Part 2 wires it up.

## Branch name
`feat/fastmcp-datetime-server`

## What to build
A self-contained MCP server process that Part 2's orchestrator will spawn as a subprocess.

**Layers touched:** `mcp/datetime_server.py`

**Tool to expose:**
```python
@mcp.tool()
def normalize_date(date_text: str) -> str:
    """
    Parse a natural-language date string and return it in ISO 8601 format (YYYY-MM-DD).
    Returns an error string if the date cannot be parsed.
    """
```

**Implementation:**
- Use `fastmcp` (`from mcp.server.fastmcp import FastMCP`)
- Use `dateutil.parser.parse()` (from `python-dateutil`) to handle varied formats ("16 February 2024", "February 16, 2024", "16 Feb 24", etc.)
- Return `date.isoformat()` on success; return `f"ERROR: could not parse '{date_text}'"` on failure (do not raise)
- Run with `mcp.run(transport="stdio")` in `if __name__ == "__main__"`
- Add `python-dateutil` to `pyproject.toml` if not already present

**Manual test:**
```bash
echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"normalize_date","arguments":{"date_text":"16 February 2024"}},"id":1}' \
  | uv run mcp/datetime_server.py
```

## Acceptance criteria
- [x] Server starts without error: `uv run mcp/datetime_server.py`
- [x] `normalize_date("16 February 2024")` returns `"2024-02-16"`
- [x] `normalize_date("February 2024")` returns a best-effort date or a clear ERROR string (not a crash)
- [x] `normalize_date("not a date at all")` returns an ERROR string without raising an exception
- [x] Server is listed in MCP tool discovery (`tools/list` response includes `normalize_date`)

## Implementation notes
- `mcp/__init__.py` needed to make it a package
- `python-dateutil` is permissive; for ambiguous formats like "01/02/03" it will make assumptions — that's acceptable for this use case
- The server must not import anything from `src/utils/` to stay independently runnable

## Feature brief coverage
**Functional requirements:** FR-3

## Blocked by
- #01 — Project Scaffolding

## Status
`done`
