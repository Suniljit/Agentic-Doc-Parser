# Part 3 — LangGraph Multi-Agent Supervisor

> 🌿 **Branch:** `feat/part-3-langgraph-agent` · 📅 **Date:** 2026-05-19

## What & Why
Implement `src/part3_agent.py`: a LangGraph graph with a GPT-4o supervisor that routes queries to a Revenue Agent and/or Expenditure Agent (each backed by the ChromaDB RAG store from Part 3), then synthesizes a final answer. Demonstrates agentic graph orchestration with structured routing, parallel fan-out, and loguru-traced node transitions.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Agent loop | Single-shot RAG | One `search_document` call per agent is sufficient for the document's scope |
| Evaluation agent | None | Quality assessed by reading output; adding a 5th node is speculative complexity |
| Sub-query generation | Agent-generated inline | Supervisor only routes; each agent crafts its own focused sub-query before calling RAG |
| Parallel fan-out | List-return conditional edge | Simpler than `Send` API; both agents share the same state, no need to dispatch different payloads |
| Off-topic guardrail | Supervisor `"reject"` route | Ad-hoc input can be anything; reject path costs zero extra LLM calls and exits cleanly before any RAG |
| Input mode | CLI arg + demo fallback | `uv run src/part3_agent.py "query"` for ad-hoc; no arg runs 3 demo queries |
| Prompts | `src/prompts.yaml` (part3 section) | Consistent with Parts 1 & 2 |
| `max_completion_tokens` | supervisor=50, agents=512, synthesizer=1024 | Supervisor returns a short JSON; agents give focused answers; synthesizer combines both |

## Architecture

```
PDF ──► utils/parser.py ──► markdown ──► utils/rag.py ──► ChromaDB
                                                               │
                                                    get_retriever_tool()
                                                          (shared)
                                                               │
sys.argv[1] (or demo queries)
       │
       ▼
query ──► [START] ──► supervisor node (GPT-4o)
                           │ routes to: revenue|expenditure|both|reject
              ┌────────────┼────────────┬──────────────┐
         "revenue"      "both"    "expenditure"     "reject"
              │        (parallel)       │                │
              ▼            │            ▼                ▼
        revenue_agent ◄────┘   expenditure_agent   reject_node
        (sub-query gen          (sub-query gen      (log warning,
         + RAG + GPT-4o)        + RAG + GPT-4o)     set final_answer)
              │                       │                  │
              └──────────┬────────────┘                  │
                         ▼                               │
                   synthesizer node (GPT-4o)             │
                         │                               │
                         └──────────────┬────────────────┘
                                        ▼
                                      [END]
```

## Key Files

| File | What changes |
|---|---|
| `src/part3_agent.py` | New file — full LangGraph implementation + demo runner |
| `src/prompts.yaml` | Add `part3` section: supervisor routing, agent answer, synthesizer prompts |
| `docs/architecture.md` | Already reflects Part 3; verify after implementation |

## Implementation Plan

### Phase 1: State, graph scaffold, and supervisor node
- [ ] Define `AgentState` TypedDict with `query`, `revenue_output`, `expenditure_output`, `final_answer`, `next` fields; `next` Literal includes `"reject"`
- [ ] Load RAG store via `build_store` + `get_retriever_tool` from `utils/rag`
- [ ] Add `part3.supervisor` prompt to `prompts.yaml` (routing prompt: returns JSON `{"next": "revenue|expenditure|both|reject"}`, with clear domain description so off-topic queries get `"reject"`)
- [ ] Implement `supervisor` node: `ChatOpenAI(max_completion_tokens=50)`, parses JSON response, logs routing decision at INFO
- [ ] Implement `reject_node`: logs WARNING with the query, sets `final_answer` to a polite out-of-scope message, routes to END
- [ ] Wire conditional edge from supervisor: `"revenue"`/`"expenditure"` → single node, `"both"` → `["revenue_agent", "expenditure_agent"]`, `"reject"` → `reject_node`

### Phase 2: Revenue and Expenditure agent nodes
- [ ] Add `part3.revenue_agent` and `part3.expenditure_agent` system prompts to `prompts.yaml`
- [ ] Implement `revenue_agent` node: generate revenue-focused sub-query inline, call `search_document`, call `ChatOpenAI(max_completion_tokens=512)`, store in `revenue_output`, log chunk count + answer at DEBUG
- [ ] Implement `expenditure_agent` node: same pattern with expenditure-focused sub-query, store in `expenditure_output`
- [ ] Add edges: `revenue_agent → synthesizer`, `expenditure_agent → synthesizer`

### Phase 3: Synthesizer, CLI entry point, and demo runner
- [ ] Add `part3.synthesizer` prompt to `prompts.yaml`
- [ ] Implement `synthesizer` node: combine whichever outputs are non-empty, `ChatOpenAI(max_completion_tokens=1024)`, store in `final_answer`, log at INFO
- [ ] Add `synthesizer → END` and `reject_node → END` edges; compile graph
- [ ] Write `run_query(graph, query)` helper: calls `graph.invoke` with fully-initialized state, logs node transitions
- [ ] `if __name__ == "__main__"`: if `sys.argv[1]` present, run that single query; otherwise run all three demo queries

## Risks & Unknowns
- LangGraph list-return fan-out: returning `["revenue_agent", "expenditure_agent"]` from a conditional edge should trigger parallel execution — verify at runtime; fallback is `Send` API if this doesn't work.
- Synthesizer convergence: when only one agent ran, the other output field is `""` — prompt must handle this gracefully (instruct GPT-4o to use only available outputs).

## Edge Cases
- `"both"` routing: synthesizer must not hallucinate the missing agent's output when only one ran (guards against a supervisor mis-route being masked)
- Empty RAG results: agent node should log a warning and pass the empty string to GPT-4o rather than crashing
- Off-topic query: supervisor routes to `reject_node` before any RAG calls are made; final answer is a polite domain-boundary message

## Out of Scope
- Iterative / ReAct agent loops
- Evaluation/scoring agent
- Supervisor-generated sub-queries stored in state
- LangGraph checkpointing / persistence

## Docs to Update
- `docs/architecture.md` — verify Part 3 diagram matches final implementation
- `INDEX.md` — add link to a `docs/agent.md` deep-dive (if written post-implementation)

## Testing
- Run all three demo queries (no CLI arg) and verify routing: query 1 → both, query 2 → revenue only, query 3 → expenditure only
- Run an off-topic query via CLI arg (e.g. `"What is the weather in Singapore?"`) and confirm `reject_node` fires with no RAG calls
- Run an ad-hoc in-domain query via CLI arg and confirm correct routing + answer
- Confirm `search_document` called at least once per agent invocation (visible in DEBUG logs)
- Confirm no `print` statements; all output via `logger.info` / `logger.debug`
- Confirm `max_completion_tokens` set on all `ChatOpenAI` instantiations
