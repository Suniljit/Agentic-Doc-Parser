# LangGraph Multi-Agent Supervisor

## Summary
Implement `part3_agent.py` — a LangGraph graph with a GPT-4o supervisor that routes queries to a Revenue Agent and/or Expenditure Agent (each backed by ChromaDB RAG), then synthesizes a final answer with full routing trace logged.

## Branch name
`feat/part3-langgraph-supervisor`

## What to build
A runnable script demonstrating the multi-agent system on the target query and two additional demonstration queries.

**Layers touched:** `src/part3_agent.py`

---

### Graph state
```python
from typing import TypedDict, Literal

class AgentState(TypedDict):
    query: str
    revenue_output: str
    expenditure_output: str
    final_answer: str
    next: Literal["revenue", "expenditure", "both", "synthesize", "END"]
```

---

### Nodes

**`supervisor` node**
- Receives `query`
- Calls GPT-4o with a routing prompt: given the query, decide whether it requires `revenue`, `expenditure`, or `both` agents
- Returns `{"next": "<decision>"}` as a structured JSON response
- Log routing decision at INFO level: `"Supervisor routed to: {decision}"`

**`revenue_agent` node**
- Calls `search_document(query)` RAG tool with a revenue-focused sub-query
- Calls GPT-4o with retrieved context + system role: "You are a Revenue Agent specialising in government revenue streams, taxes, and fiscal income."
- Stores answer in `revenue_output`
- Log retrieved chunk count and answer at DEBUG level

**`expenditure_agent` node**
- Calls `search_document(query)` RAG tool with an expenditure-focused sub-query
- Calls GPT-4o with retrieved context + system role: "You are an Expenditure Agent specialising in government spending, funds, and budget allocations."
- Stores answer in `expenditure_output`
- Log retrieved chunk count and answer at DEBUG level

**`synthesizer` node**
- Receives `revenue_output` and/or `expenditure_output`
- Calls GPT-4o to combine available agent outputs into a single coherent final answer
- Stores result in `final_answer`
- Log final answer at INFO level

---

### Graph edges
```
START → supervisor
supervisor → revenue_agent     (if next == "revenue")
supervisor → expenditure_agent (if next == "expenditure")
supervisor → revenue_agent + expenditure_agent (if next == "both", parallel)
revenue_agent → synthesizer
expenditure_agent → synthesizer
synthesizer → END
```

Use a conditional edge from `supervisor` based on the `next` field. For `"both"`, use `Send` API or fan-out to both agent nodes before converging at `synthesizer`.

---

### Demonstration queries
Run the graph on all three queries and print full results:
1. `"What are the key government revenue streams, and how will the Budget for the Future Energy Fund be supported?"` (requires both agents)
2. `"What is the corporate income tax rate and how does it compare to previous years?"` (revenue only)
3. `"How much has been allocated to the Future Energy Fund and what does it cover?"` (expenditure only)

For each query, log: routing decision, which agents were invoked, final answer.

## Acceptance criteria
- [ ] Script runs end-to-end: `uv run src/part3_agent.py`
- [ ] Supervisor correctly routes query 1 to both agents, query 2 to revenue only, query 3 to expenditure only
- [ ] Each agent calls `search_document` at least once per invocation
- [ ] Final answer for query 1 addresses both revenue streams and the Future Energy Fund
- [ ] `max_completion_tokens` set on all GPT-4o calls
- [ ] Routing decision logged at INFO for each query
- [ ] Node transitions visible in loguru output (supervisor → agent(s) → synthesizer)
- [ ] No `print` statements except final answers; all logging via loguru

## Implementation notes
- `ChatOpenAI` from `langchain-openai` for LLM calls within LangGraph nodes
- Parallel fan-out for `"both"` routing: use LangGraph's `Send` API or define two outgoing conditional edges
- Each agent node creates its own focused sub-query (not just passing the raw user query) for better RAG recall
- All three GPT-4o calls per node must have explicit `max_completion_tokens`
- The `search_document` tool is shared between both agents (same ChromaDB store)

## Feature brief coverage
**Functional requirements:** FR-6, FR-7, FR-8
**Non-functional requirements:** NFR-2

## Blocked by
- #06 — ChromaDB RAG Store

## Status
`todo`
