# Multi-Agent Supervisor — Implementation Guide

> Deep-dive on `src/part3_agent.py`: graph structure, node behaviour, routing logic, and how to run it.

---

## Overview

Part 3 implements a LangGraph `StateGraph` with five nodes. A GPT-4o supervisor classifies each incoming query and routes it to one or both specialist agents, which retrieve context from ChromaDB before answering. A synthesizer combines agent outputs into a final answer.

```
query (sys.argv[1] or demo)
    │
    ▼
[START] ──► supervisor (GPT-4o) ──► route_supervisor()
                                          │
     ┌────────────────────────────────────┼──────────────────┬──────────────┐
 "revenue"                            "both"           "expenditure"    "reject"
     │                            (parallel fan-out)        │                │
     │                              ┌──────┴──────┐         │                │
     ▼                              ▼             ▼         ▼                ▼
revenue_agent ◄─────────────────────┘             └──► expenditure_agent  reject_node
(query rewrite                                        (query rewrite      (no LLM call)
 + RAG + GPT-4o)                                       + RAG + GPT-4o)
     │                                                      │                 │
     └─────────────────────────┬────────────────────────────┘                 │
                               ▼                                              │
                         synthesizer (GPT-4o) ────────────────────────────────┘
                               │
                             [END]
```

---

## State

```python
class AgentState(TypedDict):
    query: str              # original user query — never mutated after START
    revenue_output: str     # populated by revenue_agent; "" if agent did not run
    expenditure_output: str # populated by expenditure_agent; "" if agent did not run
    final_answer: str       # populated by synthesizer or reject_node
    next: Literal["revenue", "expenditure", "both", "reject"]
```

`next` is only meaningful on the `supervisor → route_supervisor` edge. Neither agent node nor `synthesizer` reads or writes it — downstream edges are unconditional, so no node needs to signal a next hop via state after the supervisor.

---

## Nodes

### `supervisor`

**LLM:** `gpt-4o`, `max_completion_tokens=64`, `temperature=0`

Receives the raw query and classifies it into one of four routing decisions: `revenue`, `expenditure`, `both`, or `reject`. The system prompt lists the document's domain (Singapore FY2024 budget — revenue streams, taxes, expenditure, funds) and maps each decision to explicit query types.

Returns JSON `{"next": "<decision>"}`. Logs routing decision at INFO.

**Why 64 tokens:** the entire output is a single JSON key-value pair; extra tokens are wasted.

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

Three sequential steps within a single node:

1. **Query rewrite** — `gpt-4o`, `max_completion_tokens=64`: rewrites the original query into a revenue-focused search query (e.g. `"corporate income tax rate FY2024 operating revenue"`). Logged at DEBUG as `Revenue agent sub-query`.
2. **RAG retrieval** — calls `search_document.invoke(sub_query)` → 4 chunks from ChromaDB. Chunk count logged at DEBUG.
3. **Answer** — `gpt-4o`, `max_completion_tokens=512`: system role `"You are a Revenue Agent specialising in Singapore government revenue streams, taxes, and fiscal income."` Receives retrieved context, the original query (for full intent), and the rewritten sub-query (as explicit scope). Telling the agent another agent handles the rest of the original question prevents it from hedging about topics outside its context. Answer logged at DEBUG; stored in `revenue_output`.

---

### `expenditure_agent`

Same three-step structure as `revenue_agent`. Rewrite prompt targets spending, allocations, and funds. System role: `"You are an Expenditure Agent specialising in Singapore government spending, funds, and budget allocations."`. Answer step receives the same context + original question + focused sub-query pattern. Answer stored in `expenditure_output`.

---

### `reject_node`

No LLM call. Logs a WARNING with the rejected query, then sets `final_answer` to a fixed out-of-scope message and routes directly to END. See [ADR-007](adr/ADR-007-single-shot-agent-design.md) for why this is a hard reject rather than a clarification loop.

---

### `synthesizer`

**LLM:** `gpt-4o`, `max_completion_tokens=1024`, `temperature=0`

Combines whichever agent outputs are non-empty into a single coherent answer. The system prompt instructs GPT-4o not to invent information and to present a single agent's output directly if only one agent ran (avoiding "the other agent found nothing" noise).

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
| `part3.supervisor` | `supervisor` node | 4-way routing classification |
| `part3.revenue_rewrite` | `revenue_agent` node (step 1) | Rewrite query for revenue-focused RAG retrieval |
| `part3.expenditure_rewrite` | `expenditure_agent` node (step 1) | Rewrite query for expenditure-focused RAG retrieval |
| `part3.revenue_agent` | `revenue_agent` node (step 3) | System role + answer instructions |
| `part3.expenditure_agent` | `expenditure_agent` node (step 3) | System role + answer instructions |
| `part3.synthesizer` | `synthesizer` node | Combine agent outputs |

---

## Token Budget

| Node / Step | `max_completion_tokens` | Rationale |
|-------------|------------------------|-----------|
| Supervisor | 64 | Single JSON key-value output |
| Revenue / Expenditure rewrite (step 1) | 64 | Rewritten search query; typically < 20 tokens |
| Revenue / Expenditure answer (step 3) | 512 | Focused domain answer; rarely needs more |
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
