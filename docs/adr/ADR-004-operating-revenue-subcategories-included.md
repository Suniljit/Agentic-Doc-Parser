# ADR-004: Subcategories of "Other Taxes" Included in Operating Revenue Tax List

**Date:** 2026-05-19  
**Status:** Accepted  
**Deciders:** Sunil

---

## Context

The assignment asks for the **"list of taxes mentioned in section 'Operating Revenue'"** (pages 5–6).

The section 1.2 narrative names the following at the top level:

> "higher collections from **Corporate Income Tax**, **Other Taxes**, **Vehicle Quota Premiums**, **Personal Income Tax**, **Assets Taxes**, and **Betting Taxes**, partially offset by lower collections from the **Goods and Services Tax**."

It then elaborates on "Other Taxes":

> "**Other Taxes**, which include the **Foreign Worker Levy**, **Water Conservation Tax**, **Land Betterment Charge**, and **Annual Tonnage Tax**…"

Two interpretations exist:

| Interpretation | Result |
|---|---|
| **Top-level only** — "Other Taxes" is one item; its subcategories are definitional detail, not separate taxes | 7 items |
| **Include subcategories** — each named tax type in the section is a distinct entry regardless of nesting | 11 items |

---

## Decision

Include subcategories. The `operating_revenue_taxes` list contains **11 items**: the 7 top-level types plus Foreign Worker Levy, Water Conservation Tax, Land Betterment Charge, and Annual Tonnage Tax.

**Rationale:** The assignment asks for taxes *mentioned* in the section, not taxes *listed at the top level*. All four subcategory names appear explicitly in the narrative text and represent real, named revenue streams. Excluding them would silently discard information the document surfaces. If the intent were top-level only, the question would more naturally ask for the "breakdown" or "line items" in the Operating Revenue table, not the narrative section.

**Assumption recorded:** This interpretation may differ from the assignment's intended answer. If grading expects only 7 top-level items, the prompt instruction `"list both the parent name and each subcategory as separate entries"` in `src/prompts.yaml` should be removed.

---

## Consequences

- `operating_revenue_taxes` always returns 11 items with `temperature=0`
- The extraction prompt explicitly instructs the model to follow the "which include" pattern, so the behaviour is deterministic and intentional
- Reversing this decision requires a one-line prompt change with no other code impact
