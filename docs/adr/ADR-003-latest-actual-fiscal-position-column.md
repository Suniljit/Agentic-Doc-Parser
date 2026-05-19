# ADR-003: "Latest Actual Fiscal Position" Maps to Actual FY2022 Column

**Date:** 2026-05-19  
**Status:** Accepted  
**Deciders:** Sunil

---

## Context

Table 1.1 (page 8) presents the Overall Fiscal Position across three dollar-value columns:

| Column | Value | Type |
|--------|-------|------|
| Actual FY2022 | 1.72 | Real collected / audited data |
| Estimated FY2023 | (0.35) | Forward projection at budget time |
| Revised FY2023 | (3.57) | Revised projection mid-year |

The target field `latest_actual_fiscal_position_bn` is defined in the assignment as **"Latest Actual Fiscal Position"**.

An initial implementation mapped this to the "Revised FY2023" column (-3.57), reasoning that it is the most recent figure in the table. This was incorrect: "Revised" is still a projection, not collected revenue. Only the "Actual FY2022" column contains verified, real fiscal data.

---

## Decision

Map `latest_actual_fiscal_position_bn` to the column whose header contains **"Actual"** → **1.72** (currently "Actual FY2022").

The extraction prompt instructs the model to find the "Actual"-labelled column without naming a specific year or position:

> "the column whose header contains 'Actual' (ignore any column labelled 'Estimated' or 'Revised'). If multiple 'Actual' columns exist, use the most recent year."

This is intentionally generalised: naming "FY2022" or "leftmost column" would hardcode assumptions that break if the document is republished with an additional "Actual FY2023" column.

---

## Consequences

- The extracted value (1.72) is the most recent year for which the Singapore government has published audited fiscal outturn data, as of the FY2024 budget document.
- The prompt generalises gracefully: if a future edition adds "Actual FY2023", the model will pick that column without any prompt change required.
