# Part 2: Tool Calling & Date Reasoning

> 🌿 **Branch:** `feat/part2-tool-calling` · 📅 **Date:** 2026-05-19

## What & Why
Build `src/part2_tool_calling.py`: parse pages 1 and 36 from the PDF, have GPT-4o extract two dates via function calling (dispatching each tool call to the FastMCP server), then classify the normalised dates against `2024-01-01` with a second GPT-4o call.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Prompt location | `prompts.yaml` (`part2.extraction`, `part2.classification`) | Consistent with Part 1; all prompts in one file |
| Missing normalize_date fallback | `null` for `normalized_date` + `null` for `status`, log WARNING | Preserves the found date in output; doesn't crash on a recoverable miss |
| Tool-call loop guard | Cap at 5 iterations | Prevents runaway loop; generous for 2 dates |
| tool_choice | `"auto"` | GPT-4o calls the tool naturally; forced choice risks over-calling |

## Architecture

```
PDF (data/fy2024_…pdf)
     │
     ▼  parse_pages([1, 36], cache_dir)          ← reuses utils/parser.py
Markdown (pages 1 + 36)
     │
     ▼  GPT-4o call #1 (tools=[normalize_date], tool_choice="auto")
     │
     ├── tool_calls returned? ──► loop (max 5 iterations)
     │       for each tool call:
     │         └─► MCP stdio client  ──►  datetime_server.py subprocess
     │                                      normalize_date(date_text) → ISO string
     │         └─► append tool result to messages
     │
     ▼  GPT-4o final message (no tool_calls)
        contains {original_text, normalized_date} pairs
     │
     ▼  GPT-4o call #2 (json_object, classification)
        classify each date against 2024-01-01
     │
     ▼  JSON output → stdout
        [{original_text, normalized_date, status}]
```

## Key Files

| File | What changes |
|---|---|
| `src/part2_tool_calling.py` | New script — full async orchestration |
| `src/prompts.yaml` | Add `part2.extraction` and `part2.classification` keys |

## Implementation Plan

### Phase 1: Prompts
- [ ] Add `part2.extraction` system prompt to `prompts.yaml` — instructs GPT-4o to find the distribution date (page 1) and estate duty date (page 36, may be inline in a sentence), and call `normalize_date` for each
- [ ] Add `part2.classification` system prompt — defines `Expired/Upcoming/Ongoing` relative to `2024-01-01`, asks for JSON array output

### Phase 2: MCP bridge
- [ ] Implement `async call_mcp_tool(tool_name, arguments) -> str` using `mcp.ClientSession` + `stdio_client`
- [ ] Log MCP round-trip duration at DEBUG level

### Phase 3: Extraction loop
- [ ] Implement `async extract_dates(client, context) -> list[dict]` 
- [ ] Define `normalize_date` tool in OpenAI function-calling format
- [ ] Build initial messages list and call GPT-4o
- [ ] Loop (max 5): on `tool_calls` response, dispatch each to `call_mcp_tool`, append tool result, re-call GPT-4o
- [ ] On loop exit: if any expected date has no tool call logged, emit `logger.warning`
- [ ] Parse final assistant message into `[{original_text, normalized_date}]` — use `null` for any date that was never normalised

### Phase 4: Classification
- [ ] Implement `async classify_dates(client, date_pairs) -> list[dict]` 
- [ ] System prompt from `prompts.yaml`; user message: the `{original_text, normalized_date}` pairs
- [ ] `response_format={"type": "json_object"}`, explicit `max_completion_tokens`
- [ ] Parse and return the JSON array

### Phase 5: Entry point
- [ ] `async def main()` — parse PDF, call extract, call classify, log result at INFO, print JSON to stdout
- [ ] `if __name__ == "__main__": asyncio.run(main())`
- [ ] `PDF_PATH`, `CACHE_DIR`, `MAX_TOKENS_EXTRACTION`, `MAX_TOKENS_CLASSIFICATION` as module-level constants

## Risks & Unknowns
- The estate duty date on page 36 is sentence-embedded ("abolished with effect from…") — the extraction prompt must explicitly handle inline date formats, not just standalone date fields
- GPT-4o may produce a final assistant message in varied formats (prose vs structured); the prompt needs to request a consistent output schema for `extract_dates` to parse reliably

## Edge Cases
- Loop hits 5 iterations without GPT-4o stopping: log WARNING with remaining unresolved tool calls, treat accumulated results as partial
- `call_mcp_tool` returns an `ERROR:` string from the server: propagate as `normalized_date: null`, log WARNING

## Out of Scope
- Retry/fallback for MCP subprocess failures
- Handling more than two dates
- `tool_choice="required"` forcing

## Docs to Update
- `docs/setup.md` — already lists `uv run src/part2_tool_calling.py`; verify MCP subprocess note is accurate after implementation
- `docs/runbook.md` — add Part 2 run notes and any DEBUG-level log tips for tracing MCP round-trips

## Testing
- Run `uv run src/part2_tool_calling.py` end-to-end and verify: two output entries, both `normalized_date` values are ISO 8601, both `status` values are valid
- Set `LOG_LEVEL=DEBUG` to confirm MCP round-trip duration appears in logs
- Confirm GPT-4o issued at least one `tool_calls` response (visible in DEBUG logs or by inserting a temporary assertion)
