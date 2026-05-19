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
- `stderr` — loguru logs at INFO level (parse progress, LLM call details, routing decisions)
- `logs/` — DEBUG-level file log for the run, e.g. `logs/2026-05-19_14-30-00_part1.log`

To suppress logs and see only the result:
```bash
uv run src/part1_extraction.py 2>/dev/null
```

To view the DEBUG log for the most recent run:
```bash
cat logs/$(ls -t logs/ | head -1)
```

To clean up all log files:
```bash
rm -rf logs/
```

---

## First-Run Setup

On the very first run, Docling downloads its layout models and parses the PDF, then calls GPT-4o once per detected chart to generate text descriptions. This takes **~60–100s + a few seconds per chart** and is a one-time cost. Subsequent runs load everything from the disk cache.

```
data/cache/
├── fy2024_analysis_of_revenue_and_expenditure.json   # DoclingDocument + chart descriptions (~5–8 MB)
├── fy2024_analysis_of_revenue_and_expenditure.md     # full markdown, no page markers (~130 KB)
└── chroma/                                           # ChromaDB vector index (Part 3 only)
    ├── chroma.sqlite3                                #   metadata + collection index
    └── <uuid>/data_level0.bin                        #   HNSW vector index
```

The cache directory is gitignored and created automatically.

---

## Cache Management

### Docling cache

#### Force a full re-parse (also re-runs GPT-4o chart description)
```bash
rm -rf data/cache/
uv run src/part1_extraction.py   # triggers re-parse on next run
```

#### Regenerate markdown only (keeps JSON and chart descriptions — no GPT-4o calls)
```bash
rm data/cache/*.md
```

#### Inspect what Docling extracted
```bash
less data/cache/fy2024_analysis_of_revenue_and_expenditure.md
```

---

## ChromaDB Store Management

The vector store is built lazily on the first run of Part 3 and persisted to `data/chroma/`. `build_store()` checks for a non-empty `chroma/` directory at startup — if it exists, the store is loaded directly with no API calls.

### Check whether the store exists
```bash
ls data/chroma/
```
If the directory is missing or empty, the next Part 3 run will build it from scratch.

### Build the store manually (without running the full Part 3 agent)
```bash
uv run python -c "
from pathlib import Path
from src.utils.rag import build_store
from src.utils.parser import parse_pdf

md = parse_pdf(Path('data/fy2024_analysis_of_revenue_and_expenditure.pdf'), Path('data/cache'))
build_store(md, Path('data/chroma'))
"
```
This embeds 61 chunks via the OpenAI embeddings API (~2s, ~$0.001) and writes the index to disk.

### Rebuild the store from scratch (re-embeds everything)

Use this after changing chunking logic in `_chunk_section` or switching embedding models.

```bash
rm -rf data/chroma/
uv run src/part3_agent.py        # rebuilds automatically on next run
```

Or rebuild manually without running the agent:
```bash
rm -rf data/chroma/
uv run python -c "
from pathlib import Path
from src.utils.rag import build_store
from src.utils.parser import parse_pdf

md = parse_pdf(Path('data/fy2024_analysis_of_revenue_and_expenditure.pdf'), Path('data/cache'))
build_store(md, Path('data/chroma'))
"
```

### Delete only the vector store (keep Docling caches)
```bash
rm -rf data/chroma/
```
The `.json` and `.md` Docling caches are untouched. The next Part 3 run re-embeds from the cached markdown — no PDF re-parse, no GPT-4o chart calls.

### Smoke-test the store (run a query directly)
```bash
uv run python -c "
from pathlib import Path
from src.utils.rag import build_store, get_retriever_tool
from src.utils.parser import parse_pdf

md = parse_pdf(Path('data/fy2024_analysis_of_revenue_and_expenditure.pdf'), Path('data/cache'))
store = build_store(md, Path('data/chroma'))
search = get_retriever_tool(store)

print(search.invoke({'query': 'Corporate Income Tax'}))
"
```

### Inspect the store contents (chunk count, collection name)
```bash
uv run python -c "
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv
load_dotenv()

store = Chroma(
    collection_name='fy2024',
    embedding_function=OpenAIEmbeddings(model='text-embedding-3-small'),
    persist_directory='data/chroma',
)
print('Chunks in store:', store._collection.count())
"
```

---

### When to rebuild vs. reload

| Scenario | Action |
|----------|--------|
| Normal Part 3 run | Nothing — store loads automatically if `chroma/` exists |
| Changed `_chunk_section` or separator logic | `rm -rf data/chroma/` then re-run |
| Switched embedding model | `rm -rf data/chroma/` then re-run |
| Docling markdown regenerated (`.md` deleted) | `rm -rf data/chroma/` then re-run — chunks will differ |
| Markdown unchanged, just re-querying | No action — existing store is reused |

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

### ChromaDB store missing or empty (Part 3)
Part 3 calls `build_store()` at startup, which creates `data/chroma/` automatically. If it fails:
- Check that `data/cache/fy2024_analysis_of_revenue_and_expenditure.md` exists (if not, run Part 1 first to trigger the Docling parse)
- Check that `OPENAI_API_KEY` is set — `build_store()` calls the embeddings API on first run
- If `data/chroma/` exists but appears corrupt, delete it and re-run: `rm -rf data/chroma/`

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
