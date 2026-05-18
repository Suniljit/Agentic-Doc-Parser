# Docling PDF Parser

## Summary
Implement `utils/parser.py` to convert the FY2024 PDF to markdown via Docling, with disk caching so subsequent runs skip re-parsing.

## Branch name
`feat/docling-pdf-parser`

## What to build
A single public function `parse_pdf(pdf_path: Path, cache_dir: Path) -> str` that all three part scripts call.

**Layers touched:** `src/utils/parser.py · data/cache/`

Two public functions:

- `parse_pdf(pdf_path: Path, cache_dir: Path) -> str` — full document markdown; used by the RAG store (ticket #06) and Part 2 (ticket #05). Caches result to `cache_dir/<stem>.md`.
- `parse_pages(pdf_path: Path, page_nums: list[int], cache_dir: Path) -> str` — concatenated markdown for specific 1-indexed pages only; used by Part 1 extraction (ticket #03) and Part 2 date extraction (ticket #05). Reads from the cached `DoclingDocument` object to avoid re-parsing.

Both call a shared internal `_get_document()` helper that parses once and caches the `DoclingDocument` (not just the markdown string) in memory or to disk.

- Log parse duration at INFO level; log cache hit/miss at DEBUG level
- Functions must be pure (no side effects beyond cache file writes)

## Acceptance criteria
- [ ] `parse_pdf(Path("data/fy2024_analysis_of_revenue_and_expenditure.pdf"), Path("data/cache"))` returns a non-empty markdown string
- [ ] Running the function twice: second call returns in <1s (cache hit)
- [ ] Returned markdown contains text from page 5 (e.g. "Corporate Income Tax")
- [ ] Returned markdown contains some representation of figure/chart content (not empty sections)
- [ ] No `print` statements; all output via loguru

## Implementation notes
- Docling is slow on first run (~30–60s for a large PDF) — the loguru INFO log on parse start sets expectations
- Cache file lives at `data/cache/fy2024_analysis_of_revenue_and_expenditure.md`; add `data/cache/` to `.gitignore`
- If Docling fails on a page (e.g. corrupt image), log a WARNING and continue — don't crash
- `data/cache/` directory should be created if it doesn't exist

## Feature brief coverage
**Functional requirements:** FR-1, FR-5
**Non-functional requirements:** NFR-1, NFR-2

## Blocked by
- #01 — Project Scaffolding

## Status
`todo`
