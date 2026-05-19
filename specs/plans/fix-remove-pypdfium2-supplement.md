# Fix: Replace pypdfium2 Supplement with Docling-Native doc.texts Pass

> 🌿 **Branch:** `fix/remove-pypdfium2-supplement` · 📅 **Date:** 2026-05-19

## What & Why

The pypdfium2 supplement step in `parse_pages()` causes cross-page text duplication: Docling joins hyphenated line-break words (e.g., `strongerthan-expected`) while pypdfium2 preserves the hyphen (`stronger-than-expected`), so the deduplication check fails and paragraph continuations from the next physical page are added again under the wrong section. Investigation confirmed that all useful content pypdfium2 was recovering — footnotes (24 items) and the cover-page footer — is already present in Docling's `DoclingDocument`, just not surfaced by `iterate_items()`.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Remove pypdfium2 supplement | Yes | Root cause of duplication; all content is in Docling |
| Source for page_footer items | `doc.texts` filtered by `label == PAGE_FOOTER` | `iterate_items()` silently skips these; `doc.texts` has them |
| `pyproject.toml` change | None | `pypdfium2` is a transitive dep of `docling`, not a direct dep |
| Scope of `doc.texts` pass | `PAGE_FOOTER` only | `iterate_items()` already yields `FOOTNOTE`, `PAGE_HEADER`, and all body text |

## Architecture

```
parse_pages()
    │
    ├─► doc.iterate_items()          ← unchanged; yields text/footnote/table/picture/caption/section_header
    │       └─► page_parts[primary_page].append(...)
    │
    ├─► doc.texts (PAGE_FOOTER pass) ← NEW: replaces pypdfium2 block
    │       └─► page_parts[primary_page].append(item.text)
    │
    └─► assemble parts               ← unchanged
```

**Removed:**
```
raw_pdf = pdfium.PdfDocument(...)    ← entire pypdfium2 block gone (~20 lines)
import pypdfium2 as pdfium           ← removed
```

## Key Files

| File | What changes |
|---|---|
| `src/utils/parser.py` | Remove `import pypdfium2`, remove supplement block (~lines 9, 169–185); add `doc.texts` pass after `iterate_items()` loop |
| `data/cache/fy2024_analysis_of_revenue_and_expenditure.md` | Delete to force regeneration |

## Implementation Plan

### Phase 1: Update parser.py
- [ ] Remove `import pypdfium2 as pdfium` (line 9)
- [ ] Remove the `all_docling_content` build block and the entire `raw_pdf`/`pdfium` supplement loop (lines ~169–185)
- [ ] After the `iterate_items()` loop in `parse_pages()`, add a `doc.texts` pass:
  ```python
  _FOOTER_LABELS = frozenset({DocItemLabel.PAGE_FOOTER})
  for item in doc.texts:
      if getattr(item, "label", None) not in _FOOTER_LABELS:
          continue
      if not item.prov:
          continue
      item_pages = {p.page_no for p in item.prov}
      if not item_pages & page_set:
          continue
      primary_page = min(item_pages & page_set)
      if item.text:
          page_parts[primary_page].append(item.text)
  ```

### Phase 2: Regenerate and verify
- [ ] Delete `data/cache/fy2024_analysis_of_revenue_and_expenditure.md`
- [ ] Run `uv run python src/utils/parser.py` and confirm no errors
- [ ] Verify "Distributed on Budget Day" appears in output (once, on page 1)
- [ ] Verify cross-page duplicates are gone:
  - `grep -c "strongerthan-expected\|stronger-than-expected" data/cache/*.md` should return 1
  - `grep -c "Tax collections are revised to" data/cache/*.md` should return 1

## Risks & Unknowns

- **Other `page_footer` items across pages**: There may be more `PAGE_FOOTER` items in `doc.texts` beyond page 1. Run `uv run python -c "from docling.datamodel.document import DoclingDocument; from pathlib import Path; doc = DoclingDocument.model_validate_json(Path('data/cache/fy2024_analysis_of_revenue_and_expenditure.json').read_text()); [print(i.prov, i.text[:60]) for i in doc.texts if str(i.label) == 'page_footer']"` to audit them before shipping. These would now appear in output; decide if any should be filtered.
- **Other PDFs**: The fix is general. For different PDFs, `doc.texts` PAGE_FOOTER items will vary — no hardcoded assumptions remain.

## Edge Cases

- `item.prov` can be empty for some footer items — guarded by `if not item.prov: continue`
- `item_pages & page_set` may be empty if the footer's page isn't in the requested set — guarded by the intersection check

## Out of Scope

- Removing `pypdfium2` as a package (it's a transitive dep, not directly declared)
- Handling `PAGE_HEADER` items (none found in this document; add only if needed)

## Docs to Update

- `docs/docling.md` — update the pypdfium2 supplement section to describe the `doc.texts` PAGE_FOOTER pass instead
- `docs/adr/` — no new ADR needed (this is a bugfix, not an architectural decision change)
- `docs/runbook.md` — remove any mention of pypdfium2 from troubleshooting steps if present

## Testing

- Regenerate markdown cache and do the two `grep` checks above (duplication gone, cover-page text present)
- Run `uv run python src/utils/parser.py 5 6` to spot-check specific pages where 1.1/1.2/1.3 sections appear and confirm no cross-section leakage
