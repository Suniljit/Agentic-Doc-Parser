# Agentic Document Parser

> **Date:** 2026-05-18  
> **Status:** Draft

---

## 1. Overview

An AI-powered pipeline that extracts structured information from a Singapore government financial PDF (FY2024 Analysis of Revenue and Expenditure), integrates external tools via MCP, and orchestrates a multi-agent system to answer complex queries. The project is structured in three parts of increasing complexity: document extraction with prompt engineering, tool-calling with date reasoning, and a LangGraph multi-agent supervisor.

---

## 2. Goals & Non-Goals

**Goals:**
- Parse a real-world financial PDF containing text, tables, and charts into LLM-consumable markdown using Docling
- Extract five specific structured fields from the document using GPT-4o with a single Pydantic-validated call
- Expose a date normalisation tool as a local FastMCP server and demonstrate LLM tool-calling via OpenAI's function-calling API
- Classify extracted dates against a reference date using LLM reasoning
- Build a LangGraph multi-agent supervisor with Revenue and Expenditure agents backed by ChromaDB RAG
- Provide full decision traces via loguru structured logging

**Non-Goals:**
- Production deployment or API serving
- Multi-document or multi-PDF support
- UI or frontend
- Fine-tuning any model
- Evaluation/benchmarking framework

---

## 3. Background & Context

The source document is the Singapore FY2024 budget analysis PDF — a financial report with mixed content (narrative text, revenue/expenditure tables, fiscal charts). This project evaluates LLM knowledge, prompt engineering, agentic design, and practical implementation.

**Key constraints:**
- Any LLM provider is acceptable; OpenAI chosen for SDK consistency (LLM + embeddings under one key)
- Jupyter notebooks are allowed but Python scripts chosen for cleaner structure; loguru provides the inline reasoning trace that notebooks would otherwise show
- Part 3 specifies LangGraph explicitly
- MCP is optional for Part 2 but implemented to demonstrate the protocol

---

## 4. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        SHARED FOUNDATION                        │
│  utils/parser.py: Docling → Markdown                           │
│  utils/llm.py: OpenAI client (gpt-4o, text-embedding-3-small)  │
└────────────────┬────────────────────────────────────────────────┘
                 │ markdown output
     ┌───────────┼────────────────────────┐
     ▼           ▼                        ▼
┌─────────┐ ┌──────────────────┐  ┌───────────────────────────────┐
│  PART 1 │ │     PART 2       │  │           PART 3              │
│         │ │                  │  │                               │
│ GPT-4o  │ │ FastMCP Server   │  │  ChromaDB (RAG)               │
│ single  │ │ (datetime_server)│  │  text-embedding-3-small       │
│ call    │ │        ▲         │  │         │                     │
│         │ │        │ MCP     │  │  LangGraph Supervisor         │
│ Pydantic│ │ OpenAI │ stdio   │  │  (gpt-4o, LLM routing)        │
│ model   │ │ fn-call│         │  │    ┌────┴─────┐              │
│ output  │ │ bridge │         │  │    ▼          ▼              │
└─────────┘ │        │         │  │ Revenue   Expenditure        │
            │ GPT-4o reasons   │  │  Agent      Agent            │
            │ over dates       │  │  (RAG tool) (RAG tool)       │
            └──────────────────┘  └───────────────────────────────┘
```

---

## 5. Part Breakdown

### Part 1 — Document Extraction & Prompt Engineering

**Objective:** Extract five structured fields from the financial PDF.

**Fields to extract:**
| Field | Type | Source Page |
|-------|------|------------|
| Corporate Income Tax amount (2024) | float | 5 |
| YOY % difference of Corp Income Tax (2024) | float | 5 |
| Total amount of top-ups (2024) | float | 20 |
| List of taxes in "Operating Revenue" section | list[str] | 5–6 |
| Latest Actual Fiscal Position | float (billions) | 8 |

**Approach:**
1. Docling converts full PDF to markdown (handles text, tables, and figure descriptions)
2. Relevant page ranges extracted from markdown
3. Single GPT-4o call with all pages as context, returns a `ExtractionResult` Pydantic model
4. Prompt uses few-shot formatting and explicit field descriptions to reduce hallucination

---

### Part 2 — Tool Calling & Date Reasoning

**Objective:** Extract and normalise two dates from the PDF, then classify them using LLM reasoning.

**Dates to extract:**
- Document distribution date (page 1)
- Date relating to estate duty (page 36)

**Approach:**
1. FastMCP server (`mcp/datetime_server.py`) exposes a `normalize_date(date_text: str) -> str` tool over stdio
2. Python orchestrator defines the tool in OpenAI's function-calling format, bridges calls to the MCP client
3. GPT-4o extracts raw date strings, calls `normalize_date` via function calling, receives ISO dates
4. Second GPT-4o call reasons over normalised dates against reference date `2024-01-01`, classifying each as `Expired / Upcoming / Ongoing`

**Output format:**
```json
[
  {
    "original_text": "Distributed on Budget Day: 16 February 2024",
    "normalized_date": "2024-02-16",
    "status": "Upcoming"
  }
]
```

---

### Part 3 — Multi-Agent Supervisor (LangGraph)

**Objective:** Orchestrate a Revenue Agent and Expenditure Agent to answer a complex cross-domain query.

**Target query:**
> "What are the key government revenue streams, and how will the Budget for the Future Energy Fund be supported?"

**Approach:**
1. Docling markdown chunked by section, embedded with `text-embedding-3-small`, stored in ChromaDB
2. Both agents share the same vector store but issue different queries based on their domain
3. LangGraph graph with typed state:
   - `supervisor` node: GPT-4o classifies the query and routes to `revenue`, `expenditure`, or `both`
   - `revenue_agent` node: RAG search → GPT-4o answer on revenue topics
   - `expenditure_agent` node: RAG search → GPT-4o answer on spending/funds topics
   - `synthesizer` node: combines agent outputs into a final coherent answer
4. Full routing decisions logged at each graph step via loguru

**LangGraph state:**
```python
class AgentState(TypedDict):
    query: str
    revenue_output: str
    expenditure_output: str
    final_answer: str
    next: Literal["revenue", "expenditure", "both", "synthesize", "END"]
```

---

## 6. Functional Requirements

- FR-1: Docling must parse the FY2024 PDF and produce markdown that captures figure descriptions, table content, and narrative text
- FR-2: Part 1 extraction must return all five fields typed correctly (floats, list of strings); invalid/missing fields must raise a Pydantic validation error
- FR-3: Part 2 MCP server must be runnable as a standalone subprocess and respond to `normalize_date` calls over stdio transport
- FR-4: Part 2 reasoning must classify each date relative to `2024-01-01` and output valid JSON matching the sample format
- FR-5: Part 3 RAG store must be built from the same Docling markdown used in Parts 1 & 2 (single parse, reused)
- FR-6: Part 3 supervisor must support routing to a single agent OR both agents depending on query content
- FR-7: Every LLM call must set `max_completion_tokens` explicitly (OpenAI SDK parameter)
- FR-8: No `print` statements; all output via loguru

---

## 7. Non-Functional Requirements

- NFR-1: **Reproducibility** — Docling parse output cached to disk so repeat runs don't re-parse the PDF
- NFR-2: **Observability** — loguru logs include: Docling parse time, per-call token usage, MCP round-trip, LangGraph node transitions, final answers
- NFR-3: **Dependency management** — `uv` + `pyproject.toml` as single source of truth; `uv run` for all execution
- NFR-4: **Secret management** — API keys via environment variables only; `.env` file supported, never committed

---

## 8. Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| LLM provider | OpenAI (gpt-4o) | Single SDK covers both LLM and embeddings under one API key; avoids two-provider complexity |
| Embeddings | text-embedding-3-small | Part of OpenAI SDK; strong quality for semantic search; no additional API key |
| PDF parser | Docling | Handles text, tables, AND chart/figure content in one pass; outputs structured markdown; avoids blind spots that text-only parsers have on figure data |
| Extraction strategy | Single GPT-4o call, all fields | Fewer API calls; easier to validate as a unit; pages 5–20 fit in context window |
| Part 2 tool approach | FastMCP server (not function decorator) | Demonstrates MCP protocol knowledge, not just OpenAI tool-calling; aligns with LLM-as-orchestrator pattern |
| MCP ↔ OpenAI bridge | Python orchestrator bridges fn-call → MCP client | GPT-4o doesn't natively speak MCP; thin bridge keeps concerns separated |
| Part 3 agent memory | ChromaDB RAG (not pre-chunked context) | Agents must *search* dynamically — pre-feeding context would defeat the purpose of specialised agents that "identify and extract" |
| Supervisor routing | LLM-based (not keyword) | Demonstrates real reasoning; correctly handles ambiguous or compound queries |
| LangChain scope | Part 3 only | Avoids over-abstracting Parts 1 & 2 where direct SDK calls are simpler; LangGraph primitives genuinely useful for graph-based agent orchestration |
| Delivery format | Python scripts + loguru | Cleaner than notebooks for code review; loguru provides the inline execution trace that notebooks would show via cell outputs |

---

## 9. Out of Scope

- Jupyter notebook delivery
- RAG evaluation (precision/recall metrics)
- Streaming LLM responses
- Retry/fallback logic for API failures
- Support for PDFs other than `fy2024_analysis_of_revenue_and_expenditure.pdf`
- MCP server authentication or multi-client support
- LangGraph persistence (checkpointing across runs)

---

## 10. References

- [Docling docs](https://ds4sd.github.io/docling/)
- [FastMCP docs](https://gofastmcp.com)
- [LangGraph docs](https://langchain-ai.github.io/langgraph/)
- [OpenAI function calling](https://platform.openai.com/docs/guides/function-calling)
- [ChromaDB docs](https://docs.trychroma.com)
