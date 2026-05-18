# Project Scaffolding

## Summary
Set up the full project structure, dependency manifest, environment config, and shared OpenAI client with loguru logging — everything every subsequent ticket depends on.

## Branch name
`feat/project-scaffolding`

## What to build
End-to-end foundation that lets any part script run with `uv run src/partN_*.py`.

**Layers touched:** `pyproject.toml · src/utils/ · .env.example · .gitignore`

- `pyproject.toml` — declare all dependencies: `docling`, `openai`, `pydantic`, `loguru`, `python-dotenv`, `chromadb`, `langchain`, `langchain-openai`, `langgraph`, `mcp[cli]`, `fastmcp`
- `src/utils/llm.py` — instantiate and export a shared `OpenAI` client; configure loguru (format, level from env); define `get_client() -> OpenAI`
- `.env.example` — document required vars: `OPENAI_API_KEY`, `LOG_LEVEL`
- `.gitignore` — ensure `.env`, `__pycache__`, `.venv`, `data/cache/` are excluded
- Confirm `uv venv .venv --python 3.13 && uv sync` produces a working environment

## Acceptance criteria
- [ ] `uv sync` completes without error
- [ ] `uv run src/utils/llm.py` exits 0 and emits an INFO log line
- [ ] loguru outputs a structured log line at INFO level on import
- [ ] `.env` is in `.gitignore` and not tracked by git
- [ ] `.env.example` documents every required environment variable

## Implementation notes
- Use `uv` only — no `pip install` or `conda`
- Set `max_completion_tokens` default in `get_client()` wrapper or document it as a caller responsibility (FR-7 requires it per-call)
- `src/` should be a proper package (`src/__init__.py`) so relative imports work

## Feature brief coverage
**Functional requirements:** FR-7, FR-8
**Non-functional requirements:** NFR-3, NFR-4

## Blocked by
_None — can start immediately._

## Status
`done`
