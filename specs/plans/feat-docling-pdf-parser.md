# Docling PDF Parser

> 🌿 **Branch:** `feat/docling-pdf-parser` · 📅 **Date:** 2026-05-18

## What & Why
Implement `src/utils/parser.py` — the shared PDF parsing layer called by all three part scripts. Converts the FY2024 Singapore budget PDF to markdown via Docling and caches at two levels so repeat runs skip re-parsing.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| DoclingDocument cache | In-memory dict + JSON disk | In-memory for same-process reuse; JSON disk for cross-process speed (avoids 30–60s re-parse on second script run) |
| `parse_pdf` cache strategy | Call `_get_document()` first, then check markdown disk cache | DoclingDocument is always warm in memory after first call; markdown disk read is the fast path on second run |
| `parse_pages` disk cache | None | Fast slice from in-memory DoclingDocument; distinct page combinations don't warrant caching |
| ADR alternatives documented | PyMuPDF, pdfplumber, MarkItDown | Three most likely parsers an evaluator would consider; all rejected due to chart/figure blindness |

## Architecture

```
[PDF file]
    │
    ▼
_get_document(pdf_path, cache_dir)
    ├── 1. in-memory dict hit  → DoclingDocument (instant)
    ├── 2. JSON disk hit       → load model → DoclingDocument (~0.5s)
    └── 3. miss                → Docling parse (30–60s) → save JSON → DoclingDocument
                                        │
                    ┌───────────────────┴────────────────────┐
                    ▼                                         ▼
          parse_pdf(pdf_path, cache_dir)          parse_pages(pdf_path, page_nums, cache_dir)
              │                                          │
              ├── markdown disk hit → return str         └── extract page content from doc
              └── miss → export_to_markdown()                └── concatenate → return str
                          → write to disk → return str
```

## Key Files

| File | What changes |
|---|---|
| `src/utils/parser.py` | New file — full implementation |
| `data/cache/` | Created at runtime; gitignored |
| `docs/adr/ADR-001-docling-pdf-parser.md` | Fill in stub with rationale and alternatives |

## Implementation Plan

### Phase 1: `_get_document()` helper
- [ ] Module-level `_DOCUMENT_CACHE: dict[str, DoclingDocument]` keyed by absolute path string
- [ ] Check in-memory cache first; log DEBUG on hit
- [ ] Check `cache_dir/<stem>.json`; if present, load via `DoclingDocument.model_validate_json()`; log DEBUG on hit
- [ ] On miss: parse with `DocumentConverter().convert(str(pdf_path)).document`; log parse duration at INFO
- [ ] Save JSON to disk; insert into in-memory cache; return

### Phase 2: `parse_pdf()`
- [ ] Call `_get_document(pdf_path, cache_dir)` (fast on cache hit)
- [ ] Check `cache_dir/<stem>.md`; return if hit (log DEBUG)
- [ ] Export full markdown via `doc.export_to_markdown()`
- [ ] Write to disk; return string

### Phase 3: `parse_pages()`
- [ ] Call `_get_document(pdf_path, cache_dir)` (always fast after Phase 2)
- [ ] Extract per-page content from `doc` for each page in `page_nums`
- [ ] Wrap page extraction in try/except; log WARNING on failure, continue
- [ ] Concatenate non-empty results; return string
- [ ] **Verify:** Docling page indexing (0 vs 1) against document pages

### Phase 4: Acceptance criteria check
- [ ] Run `parse_pdf` twice; confirm second call returns in <1s
- [ ] Confirm returned markdown contains "Corporate Income Tax"
- [ ] Confirm returned markdown contains figure/chart text (not empty sections)
- [ ] Confirm no `print` statements; all output via loguru

## Risks & Unknowns
- **Docling JSON re-load API** — `DoclingDocument.model_validate_json()` is the Pydantic method; verify it works with Docling's native JSON export (`doc.model_dump_json()`)
- **Page indexing** — ticket #03 uses 1-indexed pages; Docling may use 0-indexed internally; verify before wiring `parse_pages`
- **Figure content** — if Docling doesn't capture chart values as text, page 8 fiscal position (a chart) may be empty; verify before ticket #03 depends on it

## Edge Cases
- `cache_dir` does not exist → create with `cache_dir.mkdir(parents=True, exist_ok=True)`
- PDF path is relative → resolve to absolute before use as cache key
- Single-page extraction fails → log WARNING with page number, return content from remaining pages

## Out of Scope
- Caching `parse_pages` output to disk
- Multi-PDF support
- Streaming Docling parse progress

## Docs to Update
- `docs/adr/ADR-001-docling-pdf-parser.md` — fill in stub (part of this ticket)
- `docs/setup.md` — add note on Docling first-run latency (30–60s) and `data/cache/` directory

## Testing
- **parse_pdf cache hit**: call twice in same process; second call must return in <1s
- **parse_pdf content**: assert "Corporate Income Tax" in returned markdown (page 5 sanity check)
- **parse_pages**: call with `page_nums=[5]`; assert returned string is non-empty and shorter than full markdown
- **figure content**: assert returned markdown does not have empty figure sections (chart blindness check)
