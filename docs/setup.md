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

Each part is a standalone script. All output goes to stdout (structured data) and stderr (loguru logs).

```bash
uv run src/part1_extraction.py   # Structured extraction
uv run src/part2_tool_calling.py # Tool calling & date reasoning
uv run src/part3_agent.py        # Multi-agent supervisor
```

The FastMCP server (Part 2) is spawned automatically as a subprocess — you do not need to start it manually.

## Docling Cache

On first run, Docling parses the PDF and writes the result to `data/cache/`. Subsequent runs reuse the cache, so re-parsing is skipped. The cache directory is gitignored.

To force a re-parse, delete `data/cache/`.

## Related
- [Architecture](architecture.md)
- [Feature Brief](../specs/feature-brief.md)
