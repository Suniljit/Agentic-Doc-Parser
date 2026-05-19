# ADR-002: Selective Page Extraction with Page Markers for LLM Context

**Date:** 2026-05-19  
**Status:** Accepted  
**Deciders:** Sunil

---

## Context

Part 1 of the pipeline sends a text context to GPT-4o and asks it to extract five structured fields from the FY2024 Singapore budget document. Two design questions arise when constructing that context:

1. **How much of the document should be included?** The full document is ~1,035 lines of markdown spanning 36 pages of tables, narrative text, charts, and footnotes.
2. **How should the model know where each piece of content came from?** The five target fields are spread across pages 5, 6, 8, and 20 — different content types (narrative text vs. table) and different table columns.

Without a principled answer to both questions, the model received an undifferentiated blob of text, picked values from the wrong pages, and selected incorrect table columns. Observed failures:

- `corporate_income_tax_2024` returned 29.81 (from a different table) instead of 28.4 (stated in page 5 narrative)
- `corp_tax_yoy_pct_2024` returned 5.0 instead of 17.0 (same cause)
- `operating_revenue_taxes` returned 14 table-row items instead of the 11 types named in the page 5–6 narrative
- `latest_actual_fiscal_position_bn` returned 1.7 (Actual FY2022 column) instead of -3.57 (Revised FY2023 column)

---

## Decision A: Send only the pages required for extraction, not the full document

Pass only pages 5, 6, 8, and 20 to `parse_pages()` — the exact pages cited in the assignment for each target field.

**Rationale:**
- The document contains FY2022, FY2023 estimated, FY2023 revised, and FY2024 estimated figures across many tables. Including the full document introduces tables with similar structure but different fiscal years, increasing the chance the model fixates on the wrong row or year.
- Fewer tokens in context reduces the chance of the model losing track of the relevant section mid-completion.
- The five target fields are fully answerable from these four pages; no information from other pages is needed.
- Keeping the context small fits comfortably within the `MAX_TOKENS=512` response budget.

**Trade-off accepted:**
- This approach is brittle to page number drift if the PDF is republished with different pagination. For a fixed assignment document this is acceptable.

---

## Decision B: Embed `--- Page N ---` markers in the concatenated context

`parse_pages()` groups items by their earliest overlapping requested page and inserts `--- Page N ---` headers before each new page group. Each item is labelled under `min(item_pages ∩ requested_pages)`.

**Rationale:**
- Without markers, the concatenated output is a single undifferentiated string. The model cannot match any sentence or table to a specific page, so prompt instructions like "from Page 5" are unenforceable — the model guesses.
- Page 5 contains narrative text that explicitly states Corp Income Tax ($28.4B, 17.0% YOY). Page 8 contains Table 1.1 with three numeric columns (Actual FY2022, Estimated FY2023, Revised FY2023). Without markers the model cannot distinguish these and picks the wrong source for each field.
- Adding `--- Page N ---` headers costs negligible tokens and makes page references in the prompt verifiable — the model can scan to the correct marker before reading.
- The marker format is human-readable and survives markdown rendering without ambiguity.

**Alternative considered — separate LLM calls per page:** Each page could be sent in its own completion call. This removes ambiguity entirely but multiplies API calls (and latency/cost) proportionally. For five fields across four pages this would be wasteful, and the assignment calls for a single extraction call.

---

## Consequences

**Positive:**
- Prompt field descriptions can reference exact page numbers, matching the assignment's own citations
- The model can ground its answers to the correct page section before reading values
- Incorrect table columns and cross-page confusion are eliminated

**Negative:**
- Items that span multiple pages (e.g. a table starting on page 7 and ending on page 8) are placed under the earliest overlapping requested page, which may not match where the specific row of interest physically appears in the PDF
- Markers add a small amount of overhead to the context string

**Mitigations:**
- For this document's page set [5, 6, 8, 20], all target content is correctly labelled under its assignment-cited page — verified by running `parse_pages([5])` and `parse_pages([8])` independently
- The prompt explicitly names the table and column for the page 8 fiscal position field to handle the multi-column ambiguity even after page attribution
