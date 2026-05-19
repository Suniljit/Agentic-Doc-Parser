# Fix Agent Domain Overlap

> 🌿 **Branch:** `fix/agent-domain-overlap` · 📅 **Date:** 2026-05-19

## What & Why
Revenue and Expenditure agents duplicate each other's answers when the supervisor routes to "both" — because both rewrite steps receive the full original query and retrieve overlapping content. This fix enforces hard domain isolation at three layers: routing, retrieval, and synthesis.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Supervisor decomposition | Supervisor produces sub-queries per domain in one shot | Eliminates rewrite ambiguity at source; cleaner than prompt exclusion rules alone |
| Remove rewrite LLM step | Drop `rewrite_llm` + rewrite nodes | Redundant once supervisor decomposes; simplifies the graph |
| Agent prompt isolation | Add explicit "do not answer other domain" rule | Defence-in-depth if retrieved chunks bleed across domains |
| Synthesizer dedup | Instruct synthesizer to merge identical facts | Cheap safety net for any residual overlap |

## Architecture

```
[Original Query]
      │
      ▼
[Supervisor] ──► JSON: {next, revenue_query, expenditure_query}
      │
      ├── revenue_query ──► [Revenue Agent] ──► revenue_output
      │                         (retrieves on revenue_query only)
      │
      └── expenditure_query ──► [Expenditure Agent] ──► expenditure_output
                                    (retrieves on expenditure_query only)
                                             │
                                             ▼
                                      [Synthesizer] ──► final_answer
                                      (deduplicates before merging)
```

## Key Files

| File | What changes |
|---|---|
| `src/part3_agent.py` | Add `revenue_query`/`expenditure_query` to `AgentState`; remove `rewrite_llm`; supervisor parses decomposed JSON; revenue/expenditure nodes use state sub-queries directly; bump supervisor `max_completion_tokens` to 256 |
| `src/prompts.yaml` | Rewrite `supervisor` prompt for decomposition output; strengthen `revenue_agent` and `expenditure_agent` prompts with domain exclusion; add dedup instruction to `synthesizer`; remove `revenue_rewrite` and `expenditure_rewrite` entries |

## Implementation Plan

### Phase 1 — Supervisor decomposition + AgentState
- [ ] Add `revenue_query: str` and `expenditure_query: str` to `AgentState`
- [ ] Update `supervisor` prompt in `prompts.yaml` to output `{"next": "...", "revenue_query": "...", "expenditure_query": "..."}` for all routing decisions (empty string for unused domain)
- [ ] Update `supervisor_node` to parse both fields from JSON and write them to state
- [ ] Bump supervisor `max_completion_tokens` from 64 → 256

### Phase 2 — Remove rewrite step; wire sub-queries to agents
- [ ] Delete `rewrite_llm` instance and `revenue_rewrite`/`expenditure_rewrite` prompts from `prompts.yaml`
- [ ] Update `revenue_node` to use `state["revenue_query"]` for retrieval instead of calling rewrite LLM
- [ ] Update `expenditure_node` to use `state["expenditure_query"]` for retrieval instead of calling rewrite LLM
- [ ] Update agent `HumanMessage` to pass `sub_query` from state, not from a rewrite response

### Phase 3 — Agent prompt hardening + synthesizer dedup
- [ ] Add explicit domain exclusion rule to `revenue_agent` prompt: "Do not include expenditure, spending, fund allocations, or grant information — those are handled by a separate agent."
- [ ] Add explicit domain exclusion rule to `expenditure_agent` prompt: "Do not include revenue streams, tax rates, or fiscal income information — those are handled by a separate agent."
- [ ] Add dedup instruction to `synthesizer` prompt: "If both agents returned the same fact, present it once. Do not repeat identical figures or points."

## Risks & Unknowns
- Supervisor must produce valid JSON with all four fields for every routing decision — needs robust parsing with a fallback if a field is missing
- For single-domain routing (`"next": "revenue"`), the supervisor should produce an empty string for the unused query; agents must handle empty sub-query gracefully (skip retrieval/answer)

## Edge Cases
- If supervisor produces `"next": "both"` but one sub-query is empty, treat as single-domain routing
- If supervisor JSON is malformed, fall through to `reject_node` with a warning log

## Out of Scope
- Changing the underlying RAG chunking or retrieval strategy
- Adding new agent types or routing categories

## Docs to Update
- `docs/langgraph-supervisor.md` — update graph structure diagram and node behaviour descriptions (rewrite step removed, sub-query decomposition added)
- `docs/adr/` — consider ADR-007 amendment or a new ADR-008 for the decomposition routing change

## Testing
- Run the demo query from the logs (`"What are the key government revenue streams, and how will the Budget for the Future Energy Fund be supported?"`) and verify revenue agent answer contains no expenditure content and expenditure agent answer contains no revenue stream content
- Run a revenue-only query (`"What is the GST rate?"`) — verify supervisor routes to `"revenue"` only and `expenditure_query` is empty
- Run an expenditure-only query (`"How much was allocated to the Future Energy Fund?"`) — verify supervisor routes to `"expenditure"` only and `revenue_query` is empty
- Run an off-topic query — verify `reject_node` fires and no sub-queries are generated
