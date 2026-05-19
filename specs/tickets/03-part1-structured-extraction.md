# Part 1: Structured Extraction

## Summary
Implement `part1_extraction.py` to extract five typed fields from the FY2024 PDF using a single GPT-4o call, validated against a Pydantic model.

## Branch name
`feat/part1-structured-extraction`

## What to build
A runnable script that parses the PDF (via `utils/parser.py`), slices the relevant markdown pages, and returns a validated `ExtractionResult`.

**Layers touched:** `src/part1_extraction.py`

**Pydantic model:**
```python
class ExtractionResult(BaseModel):
    corporate_income_tax_2024: float          # page 5
    corp_tax_yoy_pct_2024: float              # page 5
    total_top_ups_2024: float                 # page 20
    operating_revenue_taxes: list[str]        # pages 5–6
    latest_actual_fiscal_position_bn: float   # page 8
```

**Script behaviour:**
1. Call `parse_pdf()` to get per-page markdown content (cached); `utils/parser.py` should expose page-level access via Docling's `DoclingDocument` so callers can request specific pages without parsing markdown markers
2. Concatenate pages 5, 6, 8, and 20 into a single context string (these are the exact pages the spec cites for each field; page 7 is not needed)
3. Build a system prompt that describes each field (type, page, description) and instructs GPT-4o to return a JSON object matching the schema
4. Single `client.chat.completions.create()` call with `response_format={"type": "json_object"}` and explicit `max_completion_tokens`
5. Parse response JSON into `ExtractionResult`; let Pydantic raise on type errors
6. Log each extracted field value at INFO level
7. Print final `ExtractionResult` as pretty JSON to stdout

**Prompt requirements:**
- System prompt lists all five fields with their types, source pages, and any disambiguation notes (e.g. "YOY % should be a signed float, e.g. -2.3 for a 2.3% decrease")
- User message contains only the markdown excerpt — no instructions mixed in
- Prompt must not ask GPT-4o to explain; output JSON only

## Acceptance criteria
- [ ] Script runs end-to-end: `uv run src/part1_extraction.py`
- [ ] Output is a valid `ExtractionResult` with all five fields populated
- [ ] All numeric fields are `float`, not string
- [ ] `operating_revenue_taxes` is a non-empty list of strings
- [ ] Pydantic raises `ValidationError` if GPT-4o returns a field with wrong type (e.g. `"N/A"` for a float)
- [ ] `max_completion_tokens` is set explicitly on the API call
- [ ] No `print` statements except the final JSON output; all logging via loguru

## Implementation notes
- `utils/parser.py` (#02) should export both `parse_pdf() -> str` (full markdown, for RAG) and `parse_pages(page_nums: list[int]) -> str` (specific pages, for targeted extraction). Docling's `DoclingDocument` gives per-page access natively — use `doc.pages` rather than parsing markdown string markers, which are fragile
- Pages are 1-indexed in the spec; verify whether Docling uses 0- or 1-indexing internally
- The fiscal position (page 8) comes from a table; Docling's `TableItem` export will capture it
- The system prompt must live in `prompts.yaml` under the `part1.extraction` key, consistent with `parser.picture_description`

## Feature brief coverage
**Functional requirements:** FR-2, FR-7, FR-8

## Blocked by
- #02 — Docling PDF Parser

## Status
`done`
