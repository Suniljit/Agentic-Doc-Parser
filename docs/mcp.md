# MCP Datetime Server — Implementation Guide

> Deep-dive on `mcp/datetime_server.py`: how the FastMCP server is structured, what the `normalize_date` tool does, and how Part 2 uses it.

---

## Overview

`mcp/datetime_server.py` is a standalone [FastMCP](https://gofastmcp.com) server that exposes a single tool — `normalize_date` — over stdio transport. Part 2's orchestrator spawns it as a subprocess and communicates with it via MCP's JSON-RPC protocol.

The server has **no dependency on `src/utils/`** and can be started and tested in isolation without an OpenAI key or any other pipeline component.

---

## Data Flow

```
Part 2 orchestrator (src/part2_tool_calling.py)
    │
    │  spawns subprocess
    ▼
mcp/datetime_server.py  ← stdio transport (JSON-RPC, newline-delimited)
    │
    │  @mcp.tool()
    ▼
normalize_date(date_text: str)
    │
    ├── dateutil.parser.parse(date_text)
    │       └── returns datetime object
    │
    ├── .date().isoformat()  ──► "YYYY-MM-DD"   (success)
    │
    └── except Exception    ──► "ERROR: could not parse '...'"   (failure)
```

---

## The `normalize_date` Tool

```python
@mcp.tool()
def normalize_date(date_text: str) -> str:
    """Parse a natural-language date string and return it in ISO 8601 format (YYYY-MM-DD).
    Returns an error string if the date cannot be parsed.
    """
```

**Input:** Any natural-language date string — "16 February 2024", "Feb 16, 2024", "2024-02-16", etc.

**Output:**

| Scenario | Return value |
|----------|-------------|
| Successfully parsed | `"2024-02-16"` (ISO 8601, date only) |
| Partial date (e.g. "February 2024") | Best-effort ISO date — see [ADR-005](adr/ADR-005-date-parsing-edge-cases.md) |
| Ambiguous format (e.g. "01/02/03") | dateutil assumption applied — see [ADR-005](adr/ADR-005-date-parsing-edge-cases.md) |
| Unparseable string | `"ERROR: could not parse '<input>'"` |

The tool **never raises an exception**. All failure modes return an `ERROR:` prefixed string so the orchestrator can detect failures without catching Python exceptions across a process boundary.

---

## Transport: stdio

FastMCP's stdio transport uses newline-delimited JSON-RPC 2.0. The server reads one JSON object per line from stdin and writes one JSON object per line to stdout. Loguru debug logs go to stderr and do not interfere with the protocol.

**Initialization sequence** (required before any tool call):

```
client → {"jsonrpc":"2.0","method":"initialize","params":{...},"id":0}
server → {"jsonrpc":"2.0","id":0,"result":{"protocolVersion":"...","capabilities":{...},...}}
client → {"jsonrpc":"2.0","method":"notifications/initialized","params":{}}
```

After handshake, tool calls and discovery work normally.

---

## Running Standalone

```bash
# Start the server (blocks waiting for stdin)
uv run mcp/datetime_server.py

# Probe with a Python test client (handles the init handshake)
uv run python -c "
import subprocess, json

proc = subprocess.Popen(['uv', 'run', 'mcp/datetime_server.py'],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

def send(msg):
    proc.stdin.write(json.dumps(msg) + '\n')
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())

send({'jsonrpc':'2.0','method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'test','version':'0.1'}},'id':0})
proc.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized','params':{}}) + '\n')
proc.stdin.flush()

resp = send({'jsonrpc':'2.0','method':'tools/call','params':{'name':'normalize_date','arguments':{'date_text':'16 February 2024'}},'id':1})
print(resp['result']['content'][0]['text'])  # → 2024-02-16

proc.terminate()
"
```

---

## Implementation Notes

**Why standalone?** The MCP server runs in a separate process. If it imported from `src/utils/`, a circular import or missing env var in the child process could crash it silently. Keeping it dependency-free makes startup failures obvious and reproducible.

**Why return error strings instead of raising?** MCP serialises tool return values as content blocks. A Python exception raised inside a tool gets caught by FastMCP and returned as an error response, but the orchestrator would need to handle both the MCP error envelope *and* a possible missing `result` field. A plain error string keeps the contract simple: every call returns a string, the orchestrator checks whether it starts with `"ERROR:"`.

**Why `dateutil` and not `datetime.strptime`?** `strptime` requires the caller to know the format string in advance. The dates extracted from the PDF by GPT-4o arrive as free-form strings (e.g. "Distributed on Budget Day: 16 February 2024" after GPT strips the prefix), and the exact format varies. `dateutil.parser.parse` handles the full range without a format string.

---

## Related
- [ADR-005: Date Parsing Edge Cases](adr/ADR-005-date-parsing-edge-cases.md)
- [Architecture](architecture.md)
- [Runbook — MCP server not responding](runbook.md#mcp-server-not-responding-part-2)
- [Feature Brief — Part 2](../specs/feature-brief.md)
