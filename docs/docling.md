# Docling PDF Parser — Implementation Guide

> Deep-dive on `src/utils/parser.py`: how the PDF is parsed, how caching works, and how chart content is captured via GPT-4o.

---

## Overview

`src/utils/parser.py` is the shared parsing layer used by all three parts. It converts the FY2024 Singapore budget PDF into LLM-consumable markdown using Docling, and exposes two public functions:

| Function | Returns | Used by |
|----------|---------|---------|
| `parse_pdf(pdf_path, cache_dir)` | Full document markdown (all pages) | Part 3 (RAG ingestion) |
| `parse_pages(pdf_path, page_nums, cache_dir)` | Markdown for specific 1-indexed pages | Part 1 (fields extraction), Part 2 (date extraction) |

Both functions call `_get_document()` internally, which is the only place a Docling parse is triggered. `parse_pdf()` builds its output by calling `parse_pages()` over all pages — so the same pypdfium2 supplement (see below) applies to both.

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
                              ▼
                         parse_pages(pdf_path, page_nums, cache_dir)
                              │
                    ┌─────────┴──────────────────┐
                    │                            │
           Docling item pass               pypdfium2 supplement
           iterate_items() filtered        pdfium.PdfDocument(pdf_path)
           by prov.page_no                 page.get_textpage().get_text_range()
                    │                            │
           TableItem.export_to_markdown(doc)     └── append lines not found
           PictureItem.export_to_markdown(doc,        in Docling output
             image_mode=PLACEHOLDER)                  (e.g. footer text)
           TextItem.text
                    │
                    └─── combined per-page content with --- Page N --- markers
                              │
              ┌───────────────┴───────────────────┐
              ▼                                   ▼
       parse_pdf()                          direct callers
       (all 37 pages)                       (Parts 1 & 2)
              │
              ▼
    data/cache/<stem>.md
    (full-document markdown cache)
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
A separate cache specific to `parse_pdf`. Checked **before** calling `_get_document()`, so a second call to `parse_pdf` returns in under 1ms without loading the JSON or the DoclingDocument at all.

The `.md` file is built by calling `parse_pages()` over all 37 pages, not by `doc.export_to_markdown()`. This means it includes the pypdfium2 supplement and `--- Page N ---` markers, making it representative of the full PDF content (including text that Docling's layout analyser drops, such as cover-page footer text).

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

### Page markers

Each item is labelled under its **earliest overlapping requested page** (`min(item_pages ∩ requested_pages)`). A `--- Page N ---` separator is inserted before the first item on each new page group. This gives the consuming LLM a clear provenance signal so extraction prompts can reference pages by number (e.g. "from Page 5 narrative text"). Without markers, the concatenated output is one undifferentiated blob and the model cannot distinguish content by page. See [ADR-002](adr/ADR-002-page-markers-in-extraction-context.md) for the full rationale.

---

## pypdfium2 Supplement

Docling's layout analyser silently drops certain page regions — most notably footer text on cover pages. For example, "Distributed on Budget Day: 16 February 2024" at the bottom of page 1 is absent from the DoclingDocument entirely, even though it is present in the PDF's text layer.

After the Docling item pass, `parse_pages` runs a second pass using `pypdfium2` (a Docling transitive dependency — no new install required):

1. For each requested page, extract raw text via `page.get_textpage().get_text_range()`
2. Build a normalised flat string of everything already captured by Docling for that page
3. For each raw line not found as a substring of the Docling content, append it to that page's output

The coverage check uses normalised whitespace (`.split()` then `.join()`, lowercased) so it handles Docling's occasional whitespace differences without false positives.

**What this fixes:** footer text, isolated captions, and other text regions that Docling's layout classifier ignores.

**What it does not fix:** text embedded in scanned images (would require OCR), or text that Docling captures but renders differently (e.g. reformatted table cells — these are already covered by the normalised substring match).

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
  extraction: |
    ...
  classification: |
    ...
```

---

## Cache Files

```
data/cache/                                              (gitignored)
├── fy2024_analysis_of_revenue_and_expenditure.json     ~5–8 MB
│   └── full DoclingDocument including chart descriptions
└── fy2024_analysis_of_revenue_and_expenditure.md       ~130 KB
    └── full markdown built via parse_pages() (all 37 pages)
        includes --- Page N --- markers and pypdfium2 supplement
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
- **`parse_pages` output is not individually cached** — each call re-slices from the in-memory or JSON-loaded DoclingDocument. The full-document result is cached via `parse_pdf()` → `data/cache/<stem>.md`, but per-page subsets are recomputed each time. For the current use cases (a few pages, called once per script) this is fine.
- **Single PDF only** — `_PDF_PIPELINE_OPTIONS` is module-level and not parameterised per-file. Multi-PDF support would require refactoring `_get_document`.

---

## Related
- [ADR-001: Docling for PDF Parsing](adr/ADR-001-docling-pdf-parser.md)
- [Architecture](architecture.md)
- [Runbook — cache management](runbook.md#cache-management)
