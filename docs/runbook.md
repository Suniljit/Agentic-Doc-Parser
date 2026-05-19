# Runbook

> Operational guide for running, debugging, and maintaining the Agentic Document Parser.

---

## Running the Parser Standalone

Before running any part script, you can verify the PDF parser in isolation:

```bash
# Parse the PDF and print page 5 markdown (default)
uv run src/utils/parser.py

# Print a specific page or set of pages
uv run src/utils/parser.py 5
uv run src/utils/parser.py 5 6 8 20
```

Output: loguru logs to stderr (parse time, cache hits), page markdown to stdout.  
On first run this triggers the full Docling parse (~60–100s). Subsequent runs use the cache.

---

## Running the Pipeline

Each part is a standalone script. Run them in order, or independently.

```bash
uv run src/part1_extraction.py   # Part 1 — structured field extraction
uv run src/part2_tool_calling.py # Part 2 — date extraction + MCP tool calling
uv run src/part3_agent.py        # Part 3 — LangGraph multi-agent supervisor
```

**Output convention:**
- `stdout` — final structured result (JSON)
- `stderr` — loguru logs (parse progress, LLM call details, routing decisions)

To suppress logs and see only the result:
```bash
uv run src/part1_extraction.py 2>/dev/null
```

To see debug-level logs (cache hits, token counts, MCP round-trips):
```bash
LOG_LEVEL=DEBUG uv run src/part1_extraction.py
```

---

## First-Run Setup

On the very first run, Docling downloads its layout models and parses the PDF, then calls GPT-4o once per detected chart to generate text descriptions. This takes **~60–100s + a few seconds per chart** and is a one-time cost. Subsequent runs load everything from the disk cache.

```
data/cache/
├── fy2024_analysis_of_revenue_and_expenditure.json   # DoclingDocument + chart descriptions (~5–8 MB)
└── fy2024_analysis_of_revenue_and_expenditure.md     # full markdown with page markers + pypdfium2 supplement (~130 KB)
```

The cache directory is gitignored and created automatically.

---

## Cache Management

### Force a full re-parse (also re-runs GPT-4o chart description)
```bash
rm -rf data/cache/
uv run src/part1_extraction.py   # triggers re-parse on next run
```

### Regenerate markdown only (keeps JSON and chart descriptions — no GPT-4o calls)
```bash
rm data/cache/*.md
```

### Inspect what Docling extracted
```bash
cat data/cache/fy2024_analysis_of_revenue_and_expenditure.md | less
```

---

## Common Failures

### `OPENAI_API_KEY` not set
```
openai.AuthenticationError: No API key provided.
```
Fix: copy `.env.example` to `.env` and add your key, or export it directly:
```bash
export OPENAI_API_KEY=sk-...
```

### Docling parse hangs or times out
Docling downloads models from HuggingFace on first run. If you're on a slow connection or HF is rate-limiting:
- Wait for the download to complete (progress bar appears in logs)
- Or set `HF_TOKEN` in `.env` to bypass anonymous rate limits

### `ValidationError` from Pydantic (Part 1)
GPT-4o returned a field in the wrong type (e.g. a string where a float was expected). Check the raw LLM output in the DEBUG logs:
```bash
LOG_LEVEL=DEBUG uv run src/part1_extraction.py 2>&1 | grep "raw"
```
This usually means the prompt needs tightening or the model returned `"N/A"` for a missing value.

### MCP server not responding (Part 2)
The FastMCP datetime server is spawned as a subprocess automatically. If it crashes:
- Check stderr for `MCP` or `datetime_server` error lines
- Run the server standalone to see its output:
  ```bash
  uv run mcp/datetime_server.py
  ```

### ChromaDB collection empty (Part 3)
Part 3 builds the RAG store at startup from the Docling markdown. If the collection is empty, check that `data/cache/` exists and contains the `.md` file. If not, run Part 1 first to trigger the parse.

---

## Log Reference

| Level | What it covers |
|-------|---------------|
| `INFO` | Parse start/duration, LLM call start, agent routing decisions, final answers |
| `DEBUG` | Cache hit/miss, token usage per call, MCP round-trip timing, LangGraph node transitions |
| `WARNING` | Skipped document items (corrupt page elements), unexpected LLM output format |

Set `LOG_LEVEL` in `.env` or as an environment variable before running.

---

## Related
- [Setup Guide](setup.md)
- [Architecture](architecture.md)
- [Feature Brief](../specs/feature-brief.md)
