# RAG Store — Implementation Guide

> Deep-dive on `src/utils/rag.py`: how the Docling markdown is chunked, embedded, persisted in ChromaDB, and exposed as a LangChain tool for Part 3 agents.

---

## Overview

`src/utils/rag.py` is the RAG layer used exclusively by Part 3. It ingests the full-document markdown produced by `parse_pdf()` and exposes two public functions:

| Function | Returns | Used by |
|----------|---------|---------|
| `build_store(markdown, persist_dir)` | `Chroma` vectorstore | Part 3 agent setup |
| `get_retriever_tool(vectorstore, k=4)` | `search_document` LangChain tool | Revenue and Expenditure agents |

---

## Data Flow

```
data/cache/fy2024_analysis_of_revenue_and_expenditure.md
    │   (produced by parse_pdf — clean markdown, no page markers)
    │
    ▼
MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "section")])
    │   → 51 Documents, one per H1 section
    │     metadata["section"] = heading text (e.g. "1.2 Operating Revenue")
    │
    ▼
_chunk_section(doc) — called for every section Document
    │
    │   Split content on "  \n" (MarkdownHeaderTextSplitter's paragraph separator)
    │
    ├── Prose-only section ───────────────────────► one Document (whole section)
    │
    └── Section containing tables
            │
            ├── Each table paragraph:
            │       pop preceding prose (title) + absorb following footnotes
            │       └─► one atomic Document per table
            │
            └── Any remaining prose ──────────────► one Document
    │
    ▼
61 chunks total  (19 table, 42 prose)
metadata["section"] inherited from parent H1 section
    │
    ▼
OpenAIEmbeddings("text-embedding-3-small")
    │
    ▼
Chroma.from_documents(collection="fy2024", persist_dir="data/chroma/")
    │
    ├── build_store() → Chroma    (skips if persist_dir non-empty)
    │
    └── get_retriever_tool(k=4)
                │
                ▼
        search_document(query) → "[section]\ncontent\n\n[section]\ncontent..."
                │
                ▼
        Part 3 Revenue / Expenditure agents
```

---

## Chunking Strategy

### Phase 1 — Section splitting

`MarkdownHeaderTextSplitter` splits the markdown on every H1 heading (`# `), producing one `Document` per section. The heading text is stripped from `page_content` and stored in `metadata["section"]`.

The FY2024 markdown has only H1 headings throughout — Docling outputs a flat heading hierarchy for this document. See [ADR-006](adr/ADR-006-chunking-strategy.md) for why `##`/`###` splitting (as originally specified) would produce zero splits.

**Result:** 51 section Documents.

Sections with no body content (e.g. `# 01 Update on Financial Year 2023`, which is immediately followed by `# 1.1 ...`) are dropped silently.

---

### Phase 2 — Section chunking (`_chunk_section`)

The separator `MarkdownHeaderTextSplitter` uses between paragraphs in its output is `"  \n"` — two spaces followed by a newline. Crucially, table rows use single `\n`, so an entire table stays as one paragraph after the `"  \n"` split.

`_chunk_section` uses this to decide how to handle each section:

- **Prose-only section** (no `|` lines anywhere) → return the entire section content as one chunk. Every prose section in this document is under ~4,000 chars — well within the embedding model's limit — so further splitting would only hurt retrieval by fragmenting coherent context.
- **Section containing tables** → carve out each table as an atomic chunk; any remaining prose is kept together as one additional chunk.

#### Table carving algorithm

For sections with tables, the algorithm processes paragraphs in a single pass, using a `pending_prose` buffer:

```
pending_prose = []

for each paragraph in section:

  if paragraph is a table (any line starts with "|"):
      group = []

      ① pop the last item from pending_prose ──► prepend as table title
         if pending_prose is now non-empty ──► flush remainder as one prose chunk

      ② append table rows

      ③ look ahead: while next paragraph is NOT a table:
            if next-next paragraph IS a table:
                stop  ──► that paragraph is the next table's title
            else:
                absorb paragraph  ──► footnote / note / duplicate label

      emit group as one atomic Document

  else (prose):
      append to pending_prose

if pending_prose is non-empty:
    emit as one prose chunk
```

The look-ahead stop condition in step ③ is the key invariant: **a prose paragraph immediately followed by a table is always a title, never a footnote.** This cleanly separates post-table footnotes from pre-next-table titles without any keyword matching.

---

### Worked example — Table 3.1a (Statistical Annex)

The Statistical Annex section contains 11 tables. Here is how `_chunk_section` processes the boundary between Table 3.1a and Table 3.1b.

**Input: paragraphs 0–6 within `# STATISTICAL ANNEX` after `"  \n"` split**

```
[0]  Table 3.1a: Overall Fiscal Position for FY2018 to FY2024 ($ million)

[1]  | BLANK BLANK                                       | FY2018  | FY2019  | ... |
     |---------------------------------------------------|---------|---------|-----|
     | Operating Revenue                                 | 73,738  | 74,274  | ... |
     | Total Expenditure                                 | 77,824  | 75,337  | ... |
     | Overall Fiscal Position                           |  3,338  |    845  | ... |
     (20 rows, single paragraph — rows separated by \n, not "  \n")

[2]  Table 3.1a: Overall Fiscal Position for FY2018 to FY2024 ($ million)
     (duplicate label — PDF layout artifact, Docling emits table labels above AND below)

[3]  Note: Figures may not add up due to rounding. Negative figures are shown in parentheses.

[4]  1 Special Transfers include Top-ups to Endowment and Trust Funds.

[5]  Table 3.1b: Overall Fiscal Position for FY2018 to FY2024 (% of GDP) 1

[6]  | BLANK BLANK                                       | FY2018  | FY2019  | ... |
     | ...                                               | 14.4%   | 14.5%   | ... |
     (table rows for 3.1b)
```

**Algorithm trace:**

| Step | i | Paragraph | Action |
|------|---|-----------|--------|
| 1 | 0 | `Table 3.1a: ...` | Prose → emit as chunk |
| 2 | 1 | `\| BLANK BLANK \| ...` | **Table detected** |
| 3 | — | — | Pop `[0]` from result → prepend to group |
| 4 | 1 | table rows | Append to group; advance i → 2 |
| 5 | 2 | `Table 3.1a: ...` (dup) | Not a table; look ahead: `[3]` = `Note:` (not a table) → **absorb** |
| 6 | 3 | `Note: Figures...` | Not a table; look ahead: `[4]` = `1 Special...` (not a table) → **absorb** |
| 7 | 4 | `1 Special Transfers...` | Not a table; look ahead: `[5]` = `Table 3.1b:` (not a table itself, but `[6]` IS a table) → **stop** |
| 8 | — | — | Emit group as one atomic Document |
| 9 | 5 | `Table 3.1b: ...` | Prose → emit as chunk |
| 10 | 6 | `\| BLANK BLANK \| ...` | **Table detected** → pop `[5]` → process Table 3.1b |

**Output chunk for Table 3.1a** (`metadata["section"] = "STATISTICAL ANNEX"`):

```
Table 3.1a: Overall Fiscal Position for FY2018 to FY2024 ($ million)

| BLANK BLANK                                                      | FY2018  | FY2019  | FY2020   | FY2021   | FY2022   | FY2023 (Revised) | FY2024 (Estimated) |
|------------------------------------------------------------------|---------|---------|----------|----------|----------|------------------|--------------------|
| Operating Revenue                                                | 73,738  | 74,274  | 67,376   | 82,487   | 91,015   | 104,301          | 108,640            |
| Tax Revenue                                                      | 66,203  | 67,645  | 61,408   | 74,761   | 82,708   | 94,960           | 99,031             |
| Total Expenditure                                                | 77,824  | 75,337  | 86,366   | 94,796   | 104,855  | 106,888          | 111,758            |
| Overall Fiscal Position                                          |  3,338  |    845  | (51,567) |  1,880   |  1,716   |  (3,571)         |    778             |
  ... (16 more rows)

Table 3.1a: Overall Fiscal Position for FY2018 to FY2024 ($ million)

Note: Figures may not add up due to rounding. Negative figures are shown in parentheses.

1 Special Transfers include Top-ups to Endowment and Trust Funds.
```

The chunk is ~3,992 chars — intact, self-describing, with title and footnotes. The LLM can map every value to its column and understands the units and rounding caveat.

---

### Why no `RecursiveCharacterTextSplitter`

All prose sections in this document are under 2,400 chars (largest: `# 2.7 Fiscal Impulse` at ~4,000 chars / ~1,000 tokens). `text-embedding-3-small` has an 8,192-token limit — every prose section fits in a single embedding call with room to spare. A size-based splitter would only help for tables, which are already handled atomically. See [ADR-006](adr/ADR-006-chunking-strategy.md).

---

## `build_store` — Embedding & Persistence

```python
vectorstore = build_store(markdown, persist_dir=Path("data/chroma"))
```

On **first call:**
1. Splits markdown into 51 sections via `_H1_SPLITTER`
2. Calls `_chunk_section` on each → 61 chunks
3. Embeds all chunks in one `Chroma.from_documents` call (OpenAI batch API)
4. Persists to `persist_dir` on disk
5. Logs chunk count and embedding duration

On **subsequent calls** (persist_dir exists and non-empty):
- Loads the existing store; no API calls, no chunking. Returns in ~10ms.

**Detecting an existing store:** `persist_dir.exists() and any(persist_dir.iterdir())`. An empty directory (e.g. from `mkdir`) is treated as missing and triggers a rebuild.

---

## `get_retriever_tool` — LangChain Tool

```python
search_tool = get_retriever_tool(vectorstore, k=4)
```

Returns a LangChain `@tool`-decorated function named `search_document`. The retriever is captured in a closure — no global state. The tool can be passed directly to a LangGraph agent's tool list.

**Return format** — each result is prefixed with its section label:

```
[STATISTICAL ANNEX]
Table 3.1a: Overall Fiscal Position for FY2018 to FY2024 ($ million)
| ... table rows ... |

[1.2 Operating Revenue]
Revised FY2023 Operating Revenue is $104.3 billion...
```

The `[section]` prefix gives the LLM provenance without embedding the heading in the chunk body itself — the heading is stripped by `MarkdownHeaderTextSplitter` and only lives in `metadata["section"]`.

If a chunk has no section label (malformed input), it falls back to `[?]`.

---

## Cache Files

```
data/cache/                    (committed — parse outputs shared in repo)
├── fy2024_*.json               DoclingDocument disk cache (~2 MB)
└── fy2024_*.md                 Full-document markdown used for RAG chunking (~109 KB)

data/chroma/                   (gitignored — binary, regeneratable)
├── chroma.sqlite3              ChromaDB index + metadata
└── <uuid>/
    └── data_level0.bin         HNSW vector index
```

**To force a full re-embed** (e.g. after changing chunking logic):
```bash
rm -rf data/chroma/
```

The markdown source (`data/cache/*.md`) is unaffected — only the vector index is deleted. The next `build_store` call re-chunks and re-embeds from the cached markdown.

---

## Chunk Statistics

| Category | Count |
|----------|-------|
| Total chunks | 61 |
| Table chunks (atomic) | 19 |
| Prose chunks (one per section) | 42 |
| H1 sections | 51 |
| Statistical Annex table chunks | 11 |
| Largest table chunk | ~6,000 chars (Table 2.1 — Ministry expenditure breakdown) |
| Largest prose chunk | ~4,000 chars (2.7 Fiscal Impulse) |

---

## Known Limitations

- **No per-agent collections** — both the Revenue Agent and Expenditure Agent query the same `fy2024` collection. Retrieval relies on query specificity to surface the right domain chunks; they are not siloed by topic.
- **Footnote heuristic may miss edge cases** — the look-ahead stop condition (`next-next is a table`) handles all observed patterns in this document but could be fooled by a multi-sentence note between two tables if the intervening "prose followed by a table" happened to be misidentified.
- **Single document only** — the collection name `fy2024` and the `persist_dir` are not parameterised. Multi-document support would require refactoring both.
- **Duplicate table labels in chunks** — Docling emits the table caption both above and below the table (a PDF layout artifact). The duplicate is absorbed into the chunk as part of the footnote sweep. It is harmless but adds ~80 chars per table chunk.

---

## Related

- [ADR-006: H1-Only Chunking Strategy](adr/ADR-006-chunking-strategy.md)
- [Docling Parser](docling.md) — produces the markdown that `build_store` ingests
- [Architecture](architecture.md)
- [Runbook — cache management](runbook.md#cache-management)
