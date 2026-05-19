# ADR-006: H1-Only Chunking Strategy for ChromaDB RAG Store

**Status:** Accepted  
**Date:** 2026-05-19

---

## Context

The Docling-parsed markdown of `fy2024_analysis_of_revenue_and_expenditure.pdf` uses exclusively H1 (`#`) headings for all ~60 document sections (e.g. `# 1.2 Operating Revenue`, `# 2.6 Special Transfers`, `# GLOSSARY`). The only `###` headings in the file are three auto-generated sub-labels inside a single chart description (lines 555–584: `### Axes:`, `### Key Components:`, `### Trends and Insights:`).

The original ticket specified splitting on `##` and `###` via `MarkdownHeaderTextSplitter`. Applied to this document, that config produces **zero primary splits** — the entire 1065-line document becomes a single chunk.

The RAG store is used by Part 3 agents to answer targeted revenue and expenditure queries. Chunk quality directly affects retrieval precision.

---

## Decision

Two-phase chunking entirely within `src/utils/rag.py` — no changes to `src/utils/parser.py`:

**Phase 1 — Section splitting:**
```python
MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "section")])
```
Produces one `Document` per H1 section with `metadata["section"]` = heading text.

**Phase 2 — Paragraph-level splitting within each section:**

For each section Document, split content on `\n\n` into paragraphs, then:
- **Table paragraph** (any line starts with `|`): merge with the preceding paragraph (table title) and any immediately following footnote/note paragraphs → emit as one atomic Document
- **Prose paragraph**: emit as its own Document as-is

No size-based secondary splitter. All resulting Documents inherit `metadata["section"]` from their parent section.

---

## Consequences

**Good:**
- Each named section of the document becomes its own retrievable unit, matching the document's natural semantic structure
- Section heading is captured in `metadata["section"]` and prepended as `[section]` in `search_document` results — LLM receives heading context without it being duplicated in chunk body
- Tables are kept intact — no mid-row splits that would make column headers ambiguous
- Table title (e.g. "Table 3.1a: Overall Fiscal Position...") and trailing footnotes/notes travel with the table in one chunk, giving the LLM full context

**Neutral:**
- Table chunks have no upper size cap — Statistical Annex tables are 3,000–6,000 chars each. Acceptable since the embedding model (`text-embedding-3-small`, 8,192-token limit) handles them comfortably and table integrity matters more than chunk uniformity
- The three `###` sub-labels in the chart description are absorbed into their parent H1 chunk rather than split further — acceptable since they are sub-labels within one chart, not independent topics
- No noise filtering applied to cover/contents sections — these are unlikely to rank highly for real revenue/expenditure queries

**Bad:**
- Footnote detection relies on a heuristic (short paragraph / starts with "Note", "1 ", "2 ") — may occasionally miss a footnote or absorb a following prose sentence. Acceptable given the specific queries this RAG store serves

---

## Alternatives Considered

| Alternative | Rejected because |
|---|---|
| Split on `##`/`###` (original ticket) | Produces zero primary splits on this document — all content becomes one chunk |
| `RecursiveCharacterTextSplitter` as secondary pass on prose | All prose sections are ≤ 2,400 chars (max: `# 2.7 Fiscal Impulse` at ~4,000 chars / ~1,000 tokens) — well within the embedding model's limit. The only genuinely large content is tables, which are already handled atomically. Adding a size-based splitter complicates the pipeline with no retrieval benefit. |
| Fix in `parser.py` using Docling's `TableItem.caption_text` / `footnotes` | Docling only populates captions for Statistical Annex tables — inline body tables have `caption_text=None`. More critically, even with grouping at parse time, the combined block is still >1000 chars and `RecursiveCharacterTextSplitter` would still split it. A `rag.py`-level fix is required regardless, making the parser change redundant. |
| Fixed-size only (no header splitting) | Loses semantic section boundaries; chunks may cut across unrelated topics |
| Filter noisy sections before embedding | Adds filtering logic and maintenance burden; noisy chunks pose negligible retrieval risk |
