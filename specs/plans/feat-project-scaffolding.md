# Project Scaffolding

> 🌿 **Branch:** `feat/project-scaffolding` · 📅 **Date:** 2026-05-18

## What & Why
Bootstrap the full dependency manifest, package structure, shared OpenAI client, and environment config so every subsequent ticket can run immediately with `uv run src/partN_*.py`.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| `get_client()` pattern | Module-level singleton | Single key + single model throughout; avoids repeated init overhead |
| loguru format | Default (no custom format string) | Minimal setup; default is already readable and timestamped |
| `mcp/` location | Top-level `mcp/` directory | MCP server is a subprocess, not imported; top-level path is unambiguous in invocation |

## Architecture

```
Agentic-Doc-Parser/
├── pyproject.toml          ← all deps declared here
├── .env.example            ← documents required env vars
├── .gitignore              ← adds .env, __pycache__, .venv, data/cache/
├── mcp/                    ← top-level (ticket 04)
│   └── datetime_server.py
└── src/
    ├── __init__.py
    ├── utils/
    │   ├── __init__.py
    │   └── llm.py          ← singleton OpenAI client + loguru config
    ├── part1_extraction.py
    ├── part2_tool_calling.py
    └── part3_supervisor.py
```

On import, `llm.py` configures loguru (level from `LOG_LEVEL` env var, default `INFO`) and exposes `client` (module-level) + `get_client() -> OpenAI`.

## Key Files

| File | What changes |
|---|---|
| `pyproject.toml` | Create with all deps: `docling`, `openai`, `pydantic`, `loguru`, `python-dotenv`, `chromadb`, `langchain`, `langchain-openai`, `langgraph`, `mcp[cli]`, `fastmcp` |
| `.env.example` | Document `OPENAI_API_KEY`, `LOG_LEVEL` |
| `.gitignore` | Add `.env`, `__pycache__/`, `.venv/`, `data/cache/` |
| `src/__init__.py` | Empty — marks `src/` as a package |
| `src/utils/__init__.py` | Empty |
| `src/utils/llm.py` | Singleton client + loguru setup |

## Implementation Plan

### Phase 1: Dependency manifest + env files
- [ ] Create `pyproject.toml` with `[project]` metadata, Python `>=3.13`, and all required deps
- [ ] Create `.env.example` with `OPENAI_API_KEY=` and `LOG_LEVEL=INFO`
- [ ] Update `.gitignore` to include `.env`, `__pycache__/`, `.venv/`, `data/cache/`
- [ ] Verify: `uv venv .venv --python 3.13 && uv sync` completes without error

### Phase 2: src/ package + shared client
- [ ] Create `src/__init__.py` (empty)
- [ ] Create `src/utils/__init__.py` (empty)
- [ ] Create `src/utils/llm.py`:
  - Load `.env` via `python-dotenv`
  - Configure loguru: remove default handler, add with level from `LOG_LEVEL` env var (default `INFO`)
  - Instantiate module-level `client = OpenAI()`
  - Define `get_client() -> OpenAI` that returns `client`
  - Log one INFO line on import to confirm setup
- [ ] Verify: `uv run src/utils/llm.py` exits 0 and emits an INFO log line

## Risks & Unknowns

- `docling` pulls in heavy ML deps (torch, transformers). `uv sync` may be slow on first run or fail on Python 3.13 if wheels aren't published yet — worth verifying early.
- `mcp[cli]` and `fastmcp` are relatively new packages; check for version conflicts with `langchain-openai` on first sync.

## Edge Cases

- `LOG_LEVEL` env var absent: default to `INFO` in `llm.py` so the import never fails even without a `.env` file.

## Out of Scope

- `src/utils/parser.py` (Docling wrapper) — ticket 02
- Any `part*.py` script stubs — subsequent tickets
- `mcp/datetime_server.py` — ticket 04

## Docs to Update

- No `INDEX.md` found at project root — skip.
- `README.md` is a stub; not in scope for this ticket (ticket 08).

## Testing

No automated tests for scaffolding — acceptance is verified manually via the two `uv run` checks in the ticket's acceptance criteria. If a future test ticket adds a `tests/` directory, `src/utils/llm.py` should be importable without side effects beyond logging.
