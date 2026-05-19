# ADR-007: Single-Shot Agent Design and Hard Rejection for Off-Topic Queries

**Status:** Accepted  
**Date:** 2026-05-19

---

## Context

Part 3 is a proof-of-concept demonstrating LangGraph multi-agent orchestration over a single PDF. It has two related design questions resolved together because they share the same root constraints:

1. **Should agents iterate?** After retrieving RAG context, can an agent decide it needs more information and call `search_document` again (ReAct loop)?
2. **How should off-topic queries be handled?** Should the system ask a clarifying question, or hard-reject and explain what it can answer?

Constraints that apply to both questions:
- **Scope:** POC — demonstrates the architecture pattern, not a production search system
- **Time:** limited development time; each additional interaction mode requires prompt engineering, testing, and graph complexity
- **Cost:** every extra LLM call has a dollar cost; iterative agents and clarification loops can multiply calls unpredictably
- **Document breadth:** the system answers questions about a single, well-scoped document (Singapore FY2024 budget); the query space is narrow and the retrieval corpus is small (61 chunks)
- **Interaction model:** the script runs in batch (CLI or demo mode); there is no conversational session or human-in-the-loop turn

---

## Decision 1 — Single-shot RAG (no iterative / ReAct loop)

Each agent calls `search_document` once, receives 4 chunks, and produces its answer in one GPT-4o call. It does not evaluate whether the retrieved context was sufficient and does not issue follow-up queries.

### Why

- **Query space is known and narrow.** The three demo queries and typical ad-hoc queries about a budget document are answerable from a handful of topically relevant chunks. Multi-hop retrieval (needing to first find one fact to know what to look for next) is uncommon in this domain.
- **61 chunks, k=4 retrieval.** The corpus is small. A well-formed sub-query reliably surfaces the right material. Each agent uses an LLM rewrite step (GPT-4o, 64 tokens) to produce a domain-focused search query before calling ChromaDB — this acts as a lightweight substitute for iterative query refinement without the cost of a loop.
- **Diminishing returns.** Iterative retrieval helps when the first pass returns irrelevant chunks. Given the chunk quality (table-aware, section-labelled) and the narrow domain, a second pass rarely changes the answer meaningfully for this document.
- **Cost and latency multiply.** A ReAct loop with a 3-iteration cap roughly triples the LLM calls per agent node (retrieve → reflect → retrieve → reflect → answer). For a POC with parallel agents, this cost compounds quickly.
- **Graph complexity.** A loop requires either a new graph node (a "reflect" node that decides whether to continue) or a node that manages its own internal loop. Both add surface area that is hard to test and debug.

### What is sacrificed

A single-shot agent will fail silently when the first retrieval misses the relevant chunk — it produces a hedged answer ("the context does not contain...") rather than retrying with a refined query. For a POC this is an acceptable trade-off; the supervisor prompt, LLM query rewrite, and k=4 retrieval together handle the common cases.

---

## Decision 2 — Hard reject for off-topic queries (no clarification loop)

When the supervisor classifies a query as `"reject"`, the graph routes to `reject_node`, which sets a fixed out-of-scope message as `final_answer` and exits. No clarifying question is generated; no agent is invoked.

### Why

**The interaction model has no reply channel.** A clarification loop requires the system to send a question back to the user and wait for a new input. This script runs in batch: one query in, one answer out. There is no session, no stdin read loop, and no conversational state carried between invocations. A generated clarification question would be logged and immediately lost — the user would have to re-read the logs and manually re-run the script with a revised query.

**Clarification prompting adds an extra LLM call for no gain.** Generating a good clarifying question requires a dedicated prompt and a GPT-4o call. The result is a string that goes nowhere useful in the current interaction model. The same cost could instead fund an extra retrieval attempt or a better supervisor prompt.

**The scope boundary is well-defined.** The system answers questions about the Singapore FY2024 budget document. A query about the weather, a recipe, or a different country's budget is unambiguously out of scope — there is nothing to clarify. A static out-of-scope message is the honest and complete response.

**Shared constraint with Decision 1.** Both iterative retrieval and clarification loops require a conversational loop that the batch script does not provide. Building that infrastructure for a POC would shift the project from "demonstrate LangGraph orchestration" to "build a chatbot framework."

### What is sacrificed

Queries that are *adjacent* to the document's scope but poorly phrased may be rejected when they could have been answered with minor rephrasing (e.g. "Singapore budget" is in scope but "global fiscal outlook" is not — a badly worded query might straddle the line). For a POC with a narrow audience and known query patterns, this edge case is acceptable.

---

## Alternatives Considered

| Alternative | Rejected because |
|---|---|
| ReAct agent loop (retrieve → reflect → retrieve → answer) | Unpredictable LLM call count; adds graph nodes; diminishing returns on a 61-chunk corpus with focused sub-queries |
| Fixed 2-iteration retry (retrieve twice, always) | Doubles agent cost on every query regardless of whether the first retrieval was sufficient |
| Clarification loop (`reject` → ask clarifying question → wait for reply) | No reply channel in batch script; requires extra LLM call; generates output that is immediately lost |
| Route ambiguous queries to `both` instead of `reject` | Would cause agents to search for budget content that doesn't exist, wasting two LLM calls and producing a "not found" answer — worse than a direct out-of-scope message |
| Let agents answer and say "I don't know" | Off-topic queries still trigger RAG calls and two agent LLM calls before producing a non-answer; adds cost and latency for a predictably useless result |
