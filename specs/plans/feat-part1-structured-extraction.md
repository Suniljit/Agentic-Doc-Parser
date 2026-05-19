# Part 1: Structured Extraction

> 🌿 **Branch:** `feat/part-1-structured-extraction` · 📅 **Date:** 2026-05-19

## What & Why
Build `src/part1_extraction.py` — a runnable script that slices four pages from the cached Docling document and makes a single GPT-4o call to extract five typed financial fields, validated with Pydantic.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| System prompt location | `prompts.yaml` under `part1.extraction` key, loaded in script | Consistent with project pattern; keeps prompt text out of Python source |
| `max_completion_tokens` | 512 | JSON with 5 short fields; 512 is safe ceiling, prevents runaway generation |
| PDF path / cache dir | Hardcoded constants | Matches existing `parser.py` `__main__` pattern; ticket says `uv run src/part1_extraction.py` (no args) |
| Logger setup | Import `get_client()` from `utils/llm.py` to trigger its logger setup | llm.py already does `logger.add(sys.stderr, ...)` — importing it is enough; no second setup needed |

## Architecture

```
uv run src/part1_extraction.py
         │
         ▼
parse_pages(pdf_path, [5,6,8,20], cache_dir)   ← utils/parser.py (cached)
         │
         ▼ markdown context string (~4 pages)
         │
  load SYSTEM_PROMPT from prompts.yaml (part1.extraction key)
         │
         ▼
client.chat.completions.create(
    model="gpt-4o",
    messages=[system, user(markdown)],
    response_format={"type": "json_object"},
    max_completion_tokens=512
)
         │
         ▼ JSON string
         │
ExtractionResult.model_validate_json(...)       ← Pydantic raises on type error
         │
         ▼
logger.info each field → print(result.model_dump_json(indent=2))
```

## Key Files

| File | What changes |
|---|---|
| `src/part1_extraction.py` | **New** — entire implementation |
| `src/prompts.yaml` | Add `part1.extraction` system prompt |
| `docs/setup.md` | Add `uv run src/part1_extraction.py` run command |
| `docs/runbook.md` | Add Part 1 entry (command, expected output, common failures) |

## Implementation Plan

### Phase 1: Core script
- [ ] Define `ExtractionResult(BaseModel)` with all 5 fields (types per ticket)
- [ ] Add `part1.extraction` prompt to `prompts.yaml` listing each field: name, type, source page, disambiguation note (signed float for YOY, billions for fiscal position)
- [ ] Load prompt in script: `SYSTEM_PROMPT = yaml.safe_load(...)["part1"]["extraction"]`
- [ ] Write `extract()` function:
  - Call `parse_pages(PDF_PATH, [5, 6, 8, 20], CACHE_DIR)` → `context`
  - Single `client.chat.completions.create()` call with `response_format={"type": "json_object"}`, `max_completion_tokens=512`, system + user messages
  - `ExtractionResult.model_validate_json(response.choices[0].message.content)`
  - `logger.info` each field value
  - `print(result.model_dump_json(indent=2))`
- [ ] `if __name__ == "__main__": extract()`

### Phase 2: Docs update
- [ ] Add Part 1 run command to `docs/setup.md`
- [ ] Add Part 1 entry to `docs/runbook.md`

## Risks & Unknowns
- **YOY sign** — prompt must explicitly say "negative float for a decrease" to avoid GPT-4o returning a positive absolute value.

## Edge Cases
- Pydantic `ValidationError` is the intended failure mode if GPT-4o returns `"N/A"` for a float — no special handling needed, let it raise.
- `operating_revenue_taxes` must be non-empty; the system prompt should instruct GPT-4o to return all tax names listed in the Operating Revenue section.

## Out of Scope
- Retry logic for API failures
- CLI argument parsing (hardcoded paths only)
- Writing results to disk

## Docs to Update
- `docs/setup.md` — run command for Part 1
- `docs/runbook.md` — Part 1 section

## Testing
- Run `uv run src/part1_extraction.py` end-to-end; confirm all 5 fields in output are correct types (floats, list of strings)
- Verify `operating_revenue_taxes` is non-empty list
- Verify no `print` outside final JSON (only `logger.*` calls in the function body)
- Manually pass a bad type to `ExtractionResult` to confirm Pydantic raises `ValidationError`
