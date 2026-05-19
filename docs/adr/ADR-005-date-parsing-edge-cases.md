# ADR-005: Accept dateutil Best-Effort Parsing for Partial and Ambiguous Dates

**Date:** 2026-05-19  
**Status:** Accepted  
**Deciders:** Sunil

---

## Context

`mcp/datetime_server.py` uses `dateutil.parser.parse()` to convert free-form date strings to ISO 8601. Two categories of input do not have a single unambiguous parse:

**Partial dates** — e.g. "February 2024" — omit the day component. `dateutil` fills in the missing day using the current day-of-month at call time (or `1` if that day does not exist in the target month). The result is a valid date, but not necessarily the one the document author intended.

**Ambiguous numeric formats** — e.g. "01/02/03" — can be interpreted as MM/DD/YY, DD/MM/YY, or YY/MM/DD depending on locale. `dateutil` defaults to U.S. convention (MM/DD/YY) unless `dayfirst=True` or `yearfirst=True` is passed. The result is deterministic but locale-dependent.

Two handling strategies were considered:

| Strategy | Partial dates | Ambiguous formats |
|----------|--------------|-----------------|
| **A — Best-effort** | Return dateutil's fill-in result as a valid ISO date | Return dateutil's MM/DD/YY assumption |
| **B — Strict** | Return `ERROR:` string when any component is missing | Return `ERROR:` string for formats with ambiguous separators |

---

## Decision

**Strategy A — accept dateutil's best-effort output** for both cases.

**Rationale:**

1. **The dates in scope are not ambiguous in context.** The two dates extracted from the FY2024 PDF (distribution date on page 1, estate duty date on page 36) are written as `"16 February 2024"` and a similar explicit format. Neither is partial or numeric-only. The edge cases are theoretical for this document.

2. **The classification task tolerates imprecision.** Part 2 classifies dates as `Expired / Upcoming / Ongoing` relative to `2024-01-01`. A one-day fill-in error on "February 2024" (day 19 vs day 1) does not change the classification outcome.

3. **Strict rejection adds complexity without benefit here.** Detecting "partial" requires inspecting the input string before passing it to dateutil (or catching a specific exception subclass that dateutil does not reliably raise for partial dates). The added complexity is not justified given that strict-rejection would still pass the same acceptance tests and the real inputs are unambiguous.

4. **Behaviour is documented and reversible.** If a future caller passes partial dates that *do* affect downstream logic, Strategy B can be applied locally by checking `dateutil.parser.parserinfo` or using a stricter parser such as `datetime.strptime` with an explicit format list. No architectural change is required.

---

## Consequences

- `normalize_date("February 2024")` returns a date in February 2024 with a fill-in day — not an ERROR string.
- `normalize_date("01/02/03")` returns `2001-02-03` (MM/DD/YY interpretation) — not an ERROR string.
- Callers that need strict validation must inspect the returned string themselves or pass already-validated input.
- If the fill-in behaviour ever causes a classification error in Part 2, the fix is to add `dayfirst`/`yearfirst` kwargs or switch to Strategy B — isolated to `datetime_server.py`.
