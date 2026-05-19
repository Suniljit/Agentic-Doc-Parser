# FastMCP Datetime Server

> 🌿 **Branch:** `feat/fastmcp-datetime-server` · 📅 **Date:** 2026-05-19

## What & Why
Build a standalone MCP server (`mcp/datetime_server.py`) that exposes a `normalize_date` tool over stdio transport. Part 2's orchestrator will spawn this as a subprocess; it must be independently runnable and testable now.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Import path | `from fastmcp import FastMCP` | `fastmcp` v2 (already in deps) exposes it here; `mcp.server.fastmcp` is the older path — verify at runtime |
| Logging | `loguru` on stderr | CLAUDE.md bans print; MCP uses stdout for protocol so stderr doesn't interfere; import loguru directly (not from `src/utils/`) |
| No pyproject.toml changes | Skip | `python-dateutil`, `fastmcp`, `mcp[cli]` already present |
| Error handling | Return string, never raise | Ticket spec; `dateutil` is permissive but can still throw on truly unparseable input |

## Architecture

```
uv run mcp/datetime_server.py
        │  (stdio)
        ▼
┌────────────────────────┐
│   FastMCP server       │
│   normalize_date(str)  │
│         │              │
│   dateutil.parse()     │
│         │              │
│   → ISO date str       │
│   → ERROR: string      │
└────────────────────────┘
```

## Key Files

| File | What changes |
|---|---|
| `mcp/__init__.py` | Create (empty — makes mcp/ a package) |
| `mcp/datetime_server.py` | Create — full MCP server implementation |

## Implementation Plan

### Phase 1: Package scaffold
- [ ] Create `mcp/__init__.py` (empty file)

### Phase 2: Server implementation
- [ ] Create `mcp/datetime_server.py`:
  - Import `FastMCP` (`from fastmcp import FastMCP`)
  - Import `dateutil.parser`, `loguru.logger`
  - Instantiate `mcp = FastMCP("datetime-server")`
  - Decorate `normalize_date(date_text: str) -> str` with `@mcp.tool()`
  - `try: dateutil.parser.parse(date_text).date().isoformat()` — return ISO string
  - `except: return f"ERROR: could not parse '{date_text}'"` — never raise
  - `if __name__ == "__main__": mcp.run(transport="stdio")`

## Edge Cases
- Partial dates like "February 2024": dateutil defaults to day=1 — acceptable per ticket
- Ambiguous formats like "01/02/03": dateutil makes assumptions — acceptable per ticket

## Out of Scope
- Authentication or multi-client support
- Integration with Part 2 orchestrator (separate ticket)
- Any import from `src/utils/`

## Docs to Update
- `docs/architecture.md` — add `mcp/datetime_server.py` to Part 2 component diagram
- `docs/runbook.md` — add `uv run mcp/datetime_server.py` run command
- `specs/tickets/04-fastmcp-datetime-server.md` — mark status `done` after implementation

## Testing
Run the manual test from the ticket to verify all acceptance criteria:
```bash
# AC2: standard date
echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"normalize_date","arguments":{"date_text":"16 February 2024"}},"id":1}' \
  | uv run mcp/datetime_server.py
# expect: "2024-02-16"

# AC4: unparseable input
echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"normalize_date","arguments":{"date_text":"not a date at all"}},"id":2}' \
  | uv run mcp/datetime_server.py
# expect: ERROR string, no crash

# AC5: tool discovery
echo '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":3}' \
  | uv run mcp/datetime_server.py
# expect: normalize_date in tools list
```
