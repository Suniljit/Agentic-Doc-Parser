# Docling PDF Parser — Implementation Guide

> Deep-dive on `src/utils/parser.py`: how the PDF is parsed, how caching works, and how chart content is captured via GPT-4o.

---

## Overview

`src/utils/parser.py` is the shared parsing layer used by all three parts. It converts the FY2024 Singapore budget PDF into LLM-consumable markdown using Docling, and exposes two public functions:

| Function | Returns | Used by |
|----------|---------|---------|
| `parse_pdf(pdf_path, cache_dir)` | Full document markdown | Part 2 (page slices), Part 3 (RAG ingestion) |
| `parse_pages(pdf_path, page_nums, cache_dir)` | Markdown for specific 1-indexed pages | Part 1 (fields extraction), Part 2 (date extraction) |

Both functions call `_get_document()` internally, which is the only place a Docling parse is triggered.

---

## Data Flow

```
PDF file
    │
    ▼
_get_document(pdf_path, cache_dir)
    │
    ├── 1. In-memory dict ──────────────────────────► DoclingDocument (instant)
    │
    ├── 2. JSON disk cache (data/cache/<stem>.json) ► DoclingDocument (~3–4s)
    │
    └── 3. Full Docling parse (~60–100s)
              │
              ├── Layout detection (text regions, tables, figures)
              ├── Table structure recognition (TableTransformer)
              ├── Figure detection → image bytes retained
              │
              └── GPT-4o vision call per chart ──► description text
                        (PictureDescriptionApiOptions)
                              │
                              ▼
                       DoclingDocument
                       (with descriptions stored in picture annotations)
                              │
                    ┌─────────┴──────────┐
                    ▼                    ▼
             parse_pdf()           parse_pages()
                    │                    │
          doc.export_to_markdown()   iterate items filtered
          (full markdown, text +     by prov.page_no
           tables + chart            │
           descriptions)             └── TableItem.export_to_markdown(doc)
                    │                    PictureItem.export_to_markdown(doc,
                    ▼                      image_mode=PLACEHOLDER)
          data/cache/<stem>.md           TextItem.text
          (markdown disk cache)
```

---

## Caching Strategy

Three cache levels, checked in order:

### Level 1 — In-memory (`_DOCUMENT_CACHE`)
Module-level dict keyed by resolved absolute path. Lives for the duration of the process. All three part scripts import `parser.py`, so a single parse serves all of them within one run.

### Level 2 — JSON disk (`data/cache/<stem>.json`)
The `DoclingDocument` is a Pydantic model. `model_dump_json()` / `model_validate_json()` round-trips it losslessly, including the GPT-4o chart descriptions stored in picture annotations. Loading takes ~3–4s — far faster than re-parsing.

### Level 3 — Full Docling parse
Triggered only when neither cache exists. Takes ~60–100s for layout analysis + one GPT-4o vision API call per chart image found in the document. Results are written to the JSON disk cache before returning.

### Markdown cache (`data/cache/<stem>.md`)
A separate, simpler cache specific to `parse_pdf`. Checked **before** calling `_get_document()`, so a second call to `parse_pdf` returns in under 1ms without loading the JSON or the DoclingDocument at all.

```
parse_pdf() on second run:
    ├── Check .md cache → HIT → return in <1ms   ✓
    └── (DoclingDocument never loaded)

parse_pages() on second run (fresh process):
    └── _get_document() → JSON cache hit → ~3–4s → extract pages → return
```

---

## Pipeline Options

Docling is configured with `PdfPipelineOptions` at module load time:

```python
_PDF_PIPELINE_OPTIONS = PdfPipelineOptions(
    generate_picture_images=True,    # retain image bytes (required for description)
    do_picture_description=True,     # run GPT-4o on each chart
    enable_remote_services=True,     # opt-in to outbound API calls
    picture_description_options=PictureDescriptionApiOptions(
        url="https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        params={"model": "gpt-4o"},
        prompt=_PROMPTS["parser"]["picture_description"],
        timeout=60.0,
    ),
)
```

**Why each flag matters:**

| Flag | Effect if omitted |
|------|-----------------|
| `generate_picture_images=True` | Chart image bytes discarded after layout detection; GPT-4o has nothing to send |
| `do_picture_description=True` | No vision call is made; chart regions become `<!-- image -->` placeholders |
| `enable_remote_services=True` | Docling raises `OperationNotAllowed` before making any outbound call |

---

## Chart Description with GPT-4o

During a full parse, Docling calls the OpenAI chat completions API once per detected figure/chart. The prompt is loaded from `src/prompts.yaml`:

```yaml
parser:
  picture_description: |
    Describe this chart or figure in detail.
    Include all visible data values, axis labels, legends, trends, and key insights.
    Focus on quantitative information — specific numbers and percentages matter.
```

The description is stored in the `PictureItem.annotations` field of the `DoclingDocument` and is serialised into the JSON cache. Subsequent runs load the description directly from JSON — GPT-4o is **not** called again.

To extract description text (rather than embedded base64 image bytes), `image_mode=ImageRefMode.PLACEHOLDER` must be passed explicitly to `PictureItem.export_to_markdown()`. The document-level `export_to_markdown()` uses `PLACEHOLDER` by default.

**Charts found in the FY2024 PDF:**

| Page | Content |
|------|---------|
| 9 | Operating Revenue breakdown (pie chart) |
| 10 | Total Expenditure allocation (pie chart) |
| 17 | Ministry expenditure comparison (bar chart) |
| 22 | Fiscal Impulse, Budget Balance and Output Gap (line chart) |

---

## `parse_pages` — Per-Page Extraction

`parse_pages` uses Docling's item-level provenance (`item.prov[].page_no`, 1-indexed) to filter content rather than slicing the markdown string. This is more reliable because markdown page markers are not part of Docling's stable API.

Item handling per type:

| Item type | How it is extracted |
|-----------|-------------------|
| `TextItem` | `item.text` |
| `TableItem` | `item.export_to_markdown(doc)` — `doc` reference required for cross-item resolution |
| `PictureItem` | `item.export_to_markdown(doc, image_mode=ImageRefMode.PLACEHOLDER)` — returns caption + GPT-4o description |

Items that span multiple pages are included if any of their pages overlap with the requested set.

---

## Prompt Management

All prompts are stored in `src/prompts.yaml` and loaded once at module import:

```python
_PROMPTS = yaml.safe_load((Path(__file__).parent.parent / "prompts.yaml").read_text())
```

The path resolves relative to `parser.py`'s location (`src/utils/`), so it works regardless of the working directory from which scripts are run.

As Parts 1, 2, and 3 are implemented, their prompts should be added under their own keys:

```yaml
parser:
  picture_description: |
    ...

part1:
  extraction_system: |
    ...

part2:
  date_classification: |
    ...
```

---

## Cache Files

```
data/cache/                                              (gitignored)
├── fy2024_analysis_of_revenue_and_expenditure.json     ~5–8 MB
│   └── full DoclingDocument including chart descriptions
└── fy2024_analysis_of_revenue_and_expenditure.md       ~100 KB
    └── full markdown exported from the DoclingDocument
```

**To force a full re-parse** (re-runs layout analysis AND GPT-4o chart calls):
```bash
rm -rf data/cache/
```

**To regenerate markdown only** (keeps chart descriptions, skips GPT-4o calls):
```bash
rm data/cache/*.md
```

---

## Known Limitations

- **First parse is slow** — Docling downloads two layout models from HuggingFace (`docling-layout-heron`, `docling-models`) on first ever run, then runs layout analysis and calls GPT-4o once per chart. Observed: ~74s on an M-series Mac after the HuggingFace models were already locally cached; add download time on a clean machine. Picture description (GPT-4o) and layout analysis (HuggingFace models) are separate steps.
- **Chart descriptions are interpretive** — GPT-4o describes what it sees, but may misread small axis labels or overlapping data points. Verify critical numeric values against the source PDF.
- **`parse_pages` is not cached to disk** — each call re-slices from the in-memory or JSON-loaded DoclingDocument. For the current use cases (a few pages, called once per script) this is fine.
- **Single PDF only** — `_PDF_PIPELINE_OPTIONS` is module-level and not parameterised per-file. Multi-PDF support would require refactoring `_get_document`.

---

## Related
- [ADR-001: Docling for PDF Parsing](adr/ADR-001-docling-pdf-parser.md)
- [Architecture](architecture.md)
- [Runbook — cache management](runbook.md#cache-management)
