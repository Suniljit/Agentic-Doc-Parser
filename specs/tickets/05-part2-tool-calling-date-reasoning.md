# Part 2: Tool-Calling & Date Reasoning

## Summary
Implement `part2_tool_calling.py` to extract two raw dates from the PDF using GPT-4o function-calling, normalise them via the FastMCP server, then classify each date relative to `2024-01-01` in a second GPT-4o call.

## Branch name
`feat/part2-tool-calling`

## What to build
A runnable script that orchestrates: PDF parsing → GPT-4o date extraction (with MCP tool call) → date classification → JSON output.

**Layers touched:** `src/part2_tool_calling.py`

---

### Step 1 — Date Extraction via Tool Calling

Define the `normalize_date` tool in OpenAI's function-calling format:
```python
tools = [{
    "type": "function",
    "function": {
        "name": "normalize_date",
        "description": "Normalize a date string to ISO 8601 (YYYY-MM-DD)",
        "parameters": {
            "type": "object",
            "properties": {
                "date_text": {"type": "string", "description": "Raw date string to normalize"}
            },
            "required": ["date_text"]
        }
    }
}]
```

Provide GPT-4o with markdown from pages 1 and 36. Instruct it to extract the two target dates and call `normalize_date` for each.

**MCP bridge:** When GPT-4o returns a `tool_calls` response, dispatch to the FastMCP server via the MCP client SDK (`mcp` package), not by calling the Python function directly. Log the MCP round-trip duration at DEBUG level.

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def call_mcp_tool(tool_name: str, arguments: dict) -> str:
    server_params = StdioServerParameters(
        command="uv", args=["run", "mcp/datetime_server.py"]
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return result.content[0].text
```

Continue the OpenAI conversation loop until no more `tool_calls` are returned.

---

### Step 2 — Date Classification

With the two normalised dates in hand, make a second GPT-4o call:
- System prompt: explain the three states (`Expired`, `Upcoming`, `Ongoing`) and the reference date `2024-01-01`
- User message: provide the list of `{original_text, normalized_date}` pairs
- Instruct GPT-4o to return a JSON array in the specified output format
- Use `response_format={"type": "json_object"}` and explicit `max_completion_tokens`

**Output format:**
```json
[
  {
    "original_text": "Distributed on Budget Day: 16 February 2024",
    "normalized_date": "2024-02-16",
    "status": "Upcoming"
  },
  {
    "original_text": "...",
    "normalized_date": "YYYY-MM-DD",
    "status": "Expired | Upcoming | Ongoing"
  }
]
```

Log the final JSON at INFO level and print it to stdout.

## Acceptance criteria
- [x] Script runs end-to-end: `uv run src/part2_tool_calling.py`
- [x] GPT-4o issues at least one `tool_calls` response during execution
- [x] MCP server is spawned as a subprocess (not called as a Python function)
- [x] Output contains exactly two date objects with `original_text`, `normalized_date`, `status` fields
- [x] Both `normalized_date` values are valid ISO 8601 strings (`YYYY-MM-DD`)
- [x] Both `status` values are one of `Expired`, `Upcoming`, `Ongoing`
- [x] MCP round-trip duration logged at DEBUG level
- [x] `max_completion_tokens` set on both GPT-4o calls
- [x] No `print` statements except final JSON output; all logging via loguru

## Implementation notes
- The script must be `async` (due to MCP client SDK); use `asyncio.run(main())` as entry point
- Pages 1 and 36 must be sliced from the Docling markdown (reuse `parse_pages()`)
- Page 1's "Distributed on Budget Day" footer text is not captured by Docling's layout analyser; `parser.py` applies a pypdfium2 supplement to recover it
- The estate duty date on page 36 may be part of a sentence (e.g. "abolished with effect from...") — the extraction prompt should handle both inline and standalone date formats
- If GPT-4o does not call `normalize_date` for a date it found, log a WARNING

## Feature brief coverage
**Functional requirements:** FR-3, FR-4, FR-7, FR-8
**Non-functional requirements:** NFR-2

## Blocked by
- #02 — Docling PDF Parser
- #04 — FastMCP Datetime Server

## Status
`done`
