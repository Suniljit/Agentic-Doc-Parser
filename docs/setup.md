# Setup & Running

## Prerequisites

- Python 3.13
- [`uv`](https://docs.astral.sh/uv/) — install via `curl -LsSf https://astral.sh/uv/install.sh | sh`
- OpenAI API key

## Install

```bash
git clone <repo-url>
cd Agentic-Doc-Parser

uv venv .venv --python 3.13
uv sync
```

## Environment

Copy `.env.example` to `.env` and fill in your key:

```bash
cp .env.example .env
```

`.env` variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | — | OpenAI API key |
| `LOG_LEVEL` | No | `INFO` | loguru log level (`DEBUG`, `INFO`, `WARNING`) |

## Running

Each part is a standalone script. All output goes to stdout (structured data) and stderr (loguru logs at INFO).

```bash
uv run src/part1_extraction.py   # Structured extraction
uv run src/part2_tool_calling.py # Tool calling & date reasoning
uv run src/part3_agent.py        # Multi-agent supervisor
```

Each run also writes a DEBUG-level log file to `logs/` (e.g. `logs/2026-05-19_14-30-00_part1.log`). The `logs/` directory is gitignored and created automatically.

The FastMCP server (Part 2) is spawned automatically as a subprocess — you do not need to start it manually.

## Docling Cache

On first run, Docling parses the PDF and writes two files to `data/cache/`:
- `<stem>.json` — serialised `DoclingDocument` including GPT-4o chart descriptions
- `<stem>.md` — full markdown export

First-run latency is **~60–100s + one GPT-4o vision API call per chart** (4 charts in this PDF). Subsequent runs skip re-parsing and re-description entirely:
- `parse_pdf` returns the cached markdown in <1ms
- `parse_pages` loads the cached `DoclingDocument` from JSON in ~3–4s

The cache directory is gitignored and created automatically. To force a full re-parse (including new GPT-4o chart calls), delete `data/cache/`.

## Related
- [Architecture](architecture.md)
- [Feature Brief](../specs/feature-brief.md)
