# ChromaDB RAG Store

> 🌿 **Branch:** `feat/chroma-db-rag` · 📅 **Date:** 2026-05-19

## What & Why
Build `src/utils/rag.py` with two public functions — `build_store()` and `get_retriever_tool()` — to chunk, embed, and persist the Docling markdown in ChromaDB, then expose a `search_document` LangChain tool for Part 3 agents.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Header split level | `#` (H1 only) | The Docling markdown contains only H1 headings — no `##`/`###` exist (except 3 inside a chart description). The ticket's `##`/`###` split would produce zero primary splits. |
| Heading in chunk body | No — heading in metadata only | `MarkdownHeaderTextSplitter` strips heading from chunk body into `metadata["section"]`. The `search_document` tool prepends `[section]` when returning results, so the LLM still sees it. |
| Noise filtering | None — embed all sections | Noisy sections (CONTENTS table, cover page) are unlikely to rank highly for real queries; filtering adds complexity for little gain. |
| Secondary split | Paragraph-level — no size-based splitter | Prose sections are all under 2,400 chars (max: `# 2.7 Fiscal Impulse` at ~4,000 chars / ~1,000 tokens); all well within `text-embedding-3-small`'s 8,192-token limit. `RecursiveCharacterTextSplitter` would only help for tables, which are already handled atomically. Removing it simplifies the pipeline with no retrieval cost. |
| New dependencies | `langchain-chroma` only | `chromadb` is already in pyproject.toml; `langchain-chroma` is a separate package. `langchain-text-splitters` is no longer needed since we dropped `RecursiveCharacterTextSplitter`. |

## Architecture

```
markdown: str
    │
    ▼
MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "section")])
    │   → one Document per H1 section, metadata["section"] = heading text
    ▼
_chunk_section(doc) — per section:
    │   split content into \n\n paragraphs
    │
    ├── paragraph contains "|" lines? (table)
    │       merge with preceding paragraph (title) +
    │       following footnote/note paragraphs
    │       → one atomic Document
    │
    └── prose paragraph?
            → one Document as-is
    │
    ▼ all section chunks (metadata["section"] inherited)
    ▼
OpenAIEmbeddings("text-embedding-3-small")
    │
    ▼
Chroma(collection="fy2024", persist_dir="data/cache/chroma/")
    │
    ├── build_store() → Chroma         (skips if persist_dir non-empty)
    └── get_retriever_tool() → Tool    (k=4, prepends [section] to results)
                │
                ▼
        Part 3 revenue / expenditure agents
```

## Key Files

| File | What changes |
|---|---|
| `src/utils/rag.py` | New — `build_store()` and `get_retriever_tool()` |
| `pyproject.toml` | Add `langchain-chroma` |
| `.gitignore` | Add `data/cache/chroma/` |
| `docs/adr/ADR-006-chunking-strategy.md` | New ADR justifying H1-only split |
| `INDEX.md` | Add ADR-006 row |

## Implementation Plan

### Phase 1: Dependencies & gitignore
- [ ] Add `langchain-chroma` to `pyproject.toml` (`langchain-text-splitters` no longer needed)
- [ ] Add `data/cache/chroma/` to `.gitignore`
- [ ] Run `uv sync` to verify clean install

### Phase 2: `build_store()`
- [ ] Implement primary split with `MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "section")])`
- [ ] Implement `_chunk_section(doc) -> list[Document]`:
  - Split `doc.page_content` by `\n\n` into paragraphs
  - Identify table paragraphs (any line starts with `|`)
  - For each table paragraph: merge with the preceding paragraph and any immediately following footnote/note paragraphs (heuristic: doesn't start with `|`, ≤ 3 lines or starts with "Note"/"1 "/"2 ")
  - For each prose paragraph: emit as its own Document
  - All resulting Documents inherit parent `metadata["section"]`
- [ ] Skip re-embedding if `persist_dir` exists and is non-empty (`os.path.exists` + `os.listdir`)
- [ ] Log chunk count and embedding duration at INFO level via loguru
- [ ] Return `Chroma` vectorstore

### Phase 3: `get_retriever_tool()`
- [ ] Create `k=4` retriever from vectorstore
- [ ] Implement `search_document` as a `@tool`-decorated function
- [ ] Return format: `"[{section}]\n{page_content}"` joined by `"\n\n"`
- [ ] Wrap retriever binding so the tool closure captures the retriever (not a global)

### Phase 4: ADR + Docs
- [ ] Write `docs/adr/ADR-006-chunking-strategy.md`
- [ ] Add ADR-006 row to `INDEX.md`

## Risks & Unknowns
- `langchain-chroma` version compatibility with installed `chromadb` — verify after `uv sync`
- The 3 `###` headings in the chart description (lines 555–584) will be absorbed into the parent H1 chunk; that's acceptable since they're sub-labels within a single chart section
- The footnote-detection heuristic (short paragraphs / starts with "Note"/"1 ") may miss some footnotes or over-eagerly absorb following prose — acceptable given the queries we're targeting

## Edge Cases
- `build_store()` must handle an already-populated `persist_dir` without re-embedding (fast path)
- Chunks with no `section` metadata fall back to `"?"` in the tool return (already in ticket spec)
- A table paragraph with no preceding paragraph (section starts directly with a table) must be handled — emit the table as-is with no title prefix

## Out of Scope
- Noise filtering of CONTENTS/cover sections
- Per-agent separate collections (both agents share `fy2024` collection)
- RAG evaluation metrics

## Docs to Update
- `INDEX.md` — add ADR-006 row
- `docs/adr/ADR-006-chunking-strategy.md` — new

## Testing
- Call `build_store()` twice; second call must return immediately without hitting OpenAI (verify via log output showing "skipping re-embedding")
- `search_document("Corporate Income Tax")` — assert at least one result contains "Corporate Income Tax"
- `search_document("Future Energy Fund")` — assert at least one result contains energy/fund text
- Assert every returned chunk has `[section]` prefix (non-empty metadata label)
