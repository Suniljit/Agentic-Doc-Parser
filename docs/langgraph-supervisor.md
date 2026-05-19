# Multi-Agent Supervisor — Implementation Guide

> Deep-dive on `src/part3_agent.py`: graph structure, node behaviour, routing logic, and how to run it.

---

## Overview

Part 3 implements a LangGraph `StateGraph` with five nodes. A GPT-4o supervisor classifies each incoming query, decomposes it into domain-scoped sub-queries, and routes to one or both specialist agents. Each agent retrieves context from ChromaDB using its pre-scoped sub-query. A synthesizer combines agent outputs into a final answer.

```
query (sys.argv[1] or demo)
    │
    ▼
[START] ──► supervisor (GPT-4o) ──► route_supervisor()
            (sets revenue_query               │
             and expenditure_query)           │
     ┌────────────────────────────────────────┼──────────────────┬──────────────┐
 "revenue"                                "both"           "expenditure"    "reject"
     │                                (parallel fan-out)        │                │
     │                                  ┌──────┴──────┐         │                │
     ▼                                  ▼             ▼         ▼                ▼
revenue_agent ◄─────────────────────────┘             └──► expenditure_agent  reject_node
(RAG + GPT-4o)                                             (RAG + GPT-4o)    (no LLM call)
     │                                                          │                │
     └─────────────────────────────┬────────────────────────────┘                │
                                   ▼                                             │
                             synthesizer (GPT-4o) ───────────────────────────────┘
                                   │
                                 [END]
```

---

## State

```python
class AgentState(TypedDict):
    query: str              # original user query — never mutated after START
    revenue_query: str      # revenue-scoped sub-query set by supervisor; "" if agent not needed
    expenditure_query: str  # expenditure-scoped sub-query set by supervisor; "" if agent not needed
    revenue_output: str     # populated by revenue_agent; "" if agent did not run
    expenditure_output: str # populated by expenditure_agent; "" if agent did not run
    final_answer: str       # populated by synthesizer or reject_node
    next: Literal["revenue", "expenditure", "both", "reject"]
```

`next` is only meaningful on the `supervisor → route_supervisor` edge. Neither agent node nor `synthesizer` reads or writes it — downstream edges are unconditional, so no node needs to signal a next hop via state after the supervisor.

---

## Nodes

### `supervisor`

**LLM:** `gpt-4o`, `max_completion_tokens=256`, `temperature=0`

Receives the raw query and in a single call: (1) classifies it into one of four routing decisions (`revenue`, `expenditure`, `both`, `reject`), and (2) produces a domain-scoped sub-query for each relevant agent.

Returns JSON:
```json
{"next": "both", "revenue_query": "GST personal income tax operating revenue FY2024", "expenditure_query": "Future Energy Fund allocation top-ups"}
```

For single-domain routing, the unused sub-query is an empty string. For `reject`, both sub-queries are empty.

`supervisor_node` applies a safety downgrade: if `next == "both"` but one sub-query is empty, it downgrades to single-domain routing. Malformed JSON falls back to `reject` with a WARNING log.

Logs routing decision at INFO. Sub-queries are passed directly to agent nodes via state — no separate rewrite step. See [ADR-008](adr/ADR-008-supervisor-query-decomposition.md).

---

### `route_supervisor`

Conditional edge function, not a node. Maps the supervisor's decision to node name(s):

```python
"both"        → ["revenue_agent", "expenditure_agent"]   # parallel fan-out
"revenue"     → "revenue_agent"
"expenditure" → "expenditure_agent"
"reject"      → "reject_node"
```

When `"both"` is returned, LangGraph runs both agents in parallel and waits for both to complete (fan-in) before scheduling `synthesizer`. Each agent writes to a different state key (`revenue_output`, `expenditure_output`), so there are no merge conflicts.

Unexpected supervisor values fall back to `"reject_node"` with a WARNING log.

---

### `revenue_agent`

Two sequential steps within a single node:

1. **RAG retrieval** — reads `state["revenue_query"]` (set by supervisor) and calls `search_document.invoke(sub_query)` → 4 chunks from ChromaDB. Sub-query and chunk count logged at INFO/DEBUG.
2. **Answer** — `gpt-4o`, `max_completion_tokens=512`: system role instructs the agent to specialise in revenue streams, taxes, and fiscal income, and **explicitly prohibits answering expenditure or fund questions** ("a separate Expenditure Agent handles those"). Receives retrieved context, the original query (for full intent), and the sub-query (as scope). Answer logged at INFO; stored in `revenue_output`.

---

### `expenditure_agent`

Same two-step structure as `revenue_agent`. Uses `state["expenditure_query"]` for retrieval. System role instructs the agent to specialise in spending, funds, and budget allocations, and **explicitly prohibits answering revenue or tax questions** ("a separate Revenue Agent handles those"). Answer stored in `expenditure_output`.

---

### `reject_node`

No LLM call. Logs a WARNING with the rejected query, then sets `final_answer` to a fixed out-of-scope message and routes directly to END. See [ADR-007](adr/ADR-007-single-shot-agent-design.md) for why this is a hard reject rather than a clarification loop.

---

### `synthesizer`

**LLM:** `gpt-4o`, `max_completion_tokens=1024`, `temperature=0`

Combines whichever agent outputs are non-empty into a single coherent answer. The system prompt instructs GPT-4o to: not invent information; deduplicate — if both agents returned the same fact or figure, present it once; present a single agent's output directly if only one agent ran (avoiding "the other agent found nothing" noise).

Logs final answer at INFO; stores in `final_answer`.

---

## Graph Wiring

```python
graph.add_edge(START, "supervisor")
graph.add_conditional_edges("supervisor", route_supervisor)   # fan-out handled here
graph.add_edge("revenue_agent", "synthesizer")
graph.add_edge("expenditure_agent", "synthesizer")
graph.add_edge("synthesizer", END)
graph.add_edge("reject_node", END)
```

LangGraph's fan-in guarantee: `synthesizer` is not scheduled until all nodes with edges pointing to it have completed. For the `"both"` case this means both agents must finish.

---

## Running

```bash
# Demo mode — runs 3 hardcoded queries covering both/revenue/expenditure routing
uv run src/part3_agent.py

# Ad-hoc query
uv run src/part3_agent.py "What is the corporate income tax rate?"

# Off-topic (triggers reject_node, no RAG or LLM agent calls)
uv run src/part3_agent.py "What is the weather in Singapore?"

# Verbose debug output (shows chunk counts, agent answers)
LOG_LEVEL=DEBUG uv run src/part3_agent.py
```

---

## Prompts

All prompts live in `src/prompts.yaml` under the `part3` key:

| Key | Used by | Purpose |
|-----|---------|---------|
| `part3.supervisor` | `supervisor` node | 4-way routing + sub-query decomposition per domain |
| `part3.revenue_agent` | `revenue_agent` node | System role, domain exclusion rules, answer instructions |
| `part3.expenditure_agent` | `expenditure_agent` node | System role, domain exclusion rules, answer instructions |
| `part3.synthesizer` | `synthesizer` node | Combine and deduplicate agent outputs |

---

## Token Budget

| Node / Step | `max_completion_tokens` | Rationale |
|-------------|------------------------|-----------|
| Supervisor | 256 | JSON with routing decision + two sub-queries |
| Revenue / Expenditure answer | 512 | Focused domain answer; rarely needs more |
| Synthesizer | 1024 | Combines up to two agent outputs |

---

## ChromaDB Dependency

`build_store` and `get_retriever_tool` are imported from `src/utils/rag.py`. The vector store is built (or loaded from cache) in `main()` before the graph is compiled, and the `search_document` tool is passed into `build_graph()` via closure — nodes do not access it through global state.

If the ChromaDB store (`data/chroma/`) does not exist, `build_store` embeds all 61 chunks on first call (~10–15s). Subsequent calls load from disk in ~10ms.

See [RAG Store](rag.md) for full chunking and embedding details.

---

## Design Decisions

- [ADR-007: Single-shot agent design and rejection handling](adr/ADR-007-single-shot-agent-design.md) — why agents do one RAG call rather than iterating, and why off-topic queries are hard-rejected rather than prompting for clarification

---

## Related

- [RAG Store](rag.md) — ChromaDB chunking, embedding, and `search_document` tool
- [Architecture](architecture.md)
- [Runbook](runbook.md)
