# Agentic Doc Parser

A three-part agentic pipeline that extracts, reasons over, and answers questions about the Singapore FY2024 Budget document (`fy2024_analysis_of_revenue_and_expenditure.pdf`) using GPT-4o, LangGraph, and ChromaDB.

---

## Architecture

Three self-contained scripts share a common foundation: a Docling-based PDF parser and an OpenAI client singleton. Each part builds on the previous concept but runs independently.

```
┌─────────────────────────────────────────────────────────┐
│                    SHARED FOUNDATION                     │
│  src/utils/llm.py    — singleton OpenAI client (gpt-4o) │
│  src/utils/parser.py — Docling + GPT-4o → markdown      │
└───────────────┬─────────────────────────────────────────┘
                │ markdown (cached to data/cache/)
    ┌───────────┼──────────────────────┐
    ▼           ▼                      ▼
┌────────┐  ┌────────────────┐  ┌─────────────────────────┐
│ PART 1 │  │     PART 2     │  │         PART 3          │
│        │  │                │  │                         │
│ GPT-4o │  │ FastMCP server │  │ ChromaDB (RAG)          │
│ single │  │ (stdio)        │  │ text-embedding-3-small  │
│ call   │  │      ▲         │  │          │              │
│        │  │      │ MCP     │  │ LangGraph Supervisor    │
│Pydantic│  │ fn-call        │  │   ┌──────┴──────┐       │
│ model  │  │      │         │  │   ▼             ▼       │
│ output │  │ GPT-4o reasons │  │ Revenue    Expenditure  │
└────────┘  │ over dates     │  │  Agent       Agent      │
            └────────────────┘  └─────────────────────────┘
```

### Part 1 — Structured Extraction (`src/part1_extraction.py`)

A single GPT-4o call in `json_object` mode extracts five typed fields from specific pages of the budget document. Output is validated against a Pydantic model. Page pre-selection (pp. 5, 6, 8, 20) keeps the context window small and the model focused.

### Part 2 — Tool Calling & Date Reasoning (`src/part2_tool_calling.py`)

GPT-4o identifies dates in the document using function calling. Each date string is dispatched to a FastMCP server over stdio, which normalises it to ISO 8601 via `python-dateutil`. A second GPT-4o call classifies each normalised date as `Upcoming` or `Expired` relative to `2024-01-01`.

### Part 3 — Multi-Agent Supervisor (`src/part3_agent.py`)

A LangGraph graph with typed state routes each query through a GPT-4o supervisor that decides whether to invoke the Revenue agent, Expenditure agent, or both in parallel. Each agent queries ChromaDB (top-k=4) for relevant chunks before answering its sub-question. A final synthesizer node merges both outputs.

```
query → supervisor → revenue_agent   → ChromaDB → GPT-4o answer ┐
                  └→ expenditure_agent → ChromaDB → GPT-4o answer ┘
                                                          ↓
                                                    synthesizer → final answer
```

---

## Setup

### Prerequisites

- Python 3.13
- [`uv`](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- OpenAI API key

### Install

```bash
git clone <repo-url>
cd Agentic-Doc-Parser

uv venv .venv --python 3.13
uv sync
```

### Environment

```bash
cp .env.example .env
# Fill in OPENAI_API_KEY
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | Yes | — | OpenAI API key |
| `LOG_LEVEL` | No | `INFO` | loguru log level (`DEBUG`, `INFO`, `WARNING`) |

### Run

```bash
uv run src/part1_extraction.py   # Structured extraction
uv run src/part2_tool_calling.py # Tool calling & date reasoning
uv run src/part3_agent.py        # Multi-agent supervisor
```

Each run writes a DEBUG-level log to `logs/` (e.g. `logs/2026-05-19_14-30-00_part1.log`). The FastMCP server for Part 2 is spawned automatically — no manual startup needed.

### First-run initialisation

**Docling cache** — created on first run of `src/part1_extraction.py` (also triggered by Parts 2 and 3 if the cache is absent). Docling parses the PDF and writes two files to `data/cache/`: a JSON snapshot of the full `DoclingDocument` (including GPT-4o chart descriptions) and a markdown export. This takes ~60–100s and makes one GPT-4o vision API call per chart (4 charts in this PDF). Subsequent runs load from cache in seconds. To force a full re-parse, delete `data/cache/`.

**ChromaDB vector store** — created on first run of `src/part3_agent.py`. The full document markdown is chunked and embedded using `text-embedding-3-small`, then written to `data/chroma/`. Subsequent runs reuse the existing store without re-embedding.

---

## Parts & Results

### Part 1 — Structured Extraction

Extracts five fields (corporate income tax, YOY change, endowment fund top-ups, operating revenue tax list, latest actual fiscal position) in a single LLM call. All five fields were extracted correctly.

→ [Full results and discussion](results/part_1/README.md)

### Part 2 — Tool Calling & Date Reasoning

Extracted two dates from pages 1 and 36, normalised them to ISO 8601 via the MCP server, and classified both correctly (`Upcoming` / `Expired`) against the `2024-01-01` reference date.

→ [Full results and discussion](results/part_2/README.md)

### Part 3 — Multi-Agent RAG

Tested four queries: two multi-domain (routed to both agents in parallel), one single-domain, one off-topic. The supervisor correctly routed all four. The multi-domain and off-topic queries were answered correctly; the single-domain query retrieved the correct allocation figure but missed coverage details due to top-k retrieval depth.

→ [Full results and discussion](results/part_3/README.md)

---

## Dependencies & Justification

| Library | Purpose | Why this one |
|---|---|---|
| `docling` | PDF parsing | The FY2024 budget PDF contains narrative text, structured tables, and charts. PyMuPDF and pdfplumber extract text and tables only — chart regions produce no output. Docling captures all three content types, ensuring charts are available as context for all parts. See [ADR-001](docs/adr/ADR-001-docling-pdf-parser.md). |
| `openai` | GPT-4o API client | GPT-4o used for extraction (Part 1), function calling (Part 2), chart description (shared), and all agent nodes (Part 3). |
| `pydantic` | Output schema validation | Enforces structured output from GPT-4o; raises immediately on malformed responses rather than silently propagating bad data. |
| `langgraph` | Multi-agent graph | Provides typed state, conditional edges, and parallel fan-out — the three primitives needed for the supervisor + parallel agent pattern in Part 3. |
| `langchain` / `langchain-openai` | LangChain integrations | Required peer dependencies for `langgraph` nodes; also provides the OpenAI embeddings wrapper for ChromaDB. |
| `langchain-chroma` / `chromadb` | Vector store | Local, zero-infrastructure vector DB. `text-embedding-3-small` embeddings are stored and queried per-agent domain. |
| `fastmcp` / `mcp` | MCP server & client | FastMCP provides a minimal decorator-based server (`@mcp.tool`); the `mcp` package provides the stdio client used by Part 2's tool loop. |
| `python-dateutil` | Date normalisation | Handles partial and ambiguous date strings (e.g. `"16 February 2024"`) without custom parsing logic. See [ADR-005](docs/adr/ADR-005-date-parsing-edge-cases.md). |
| `loguru` | Structured logging | Drop-in replacement for `logging` with structured output, level filtering, and file sink support. |
| `pyyaml` | Prompt management | All LLM prompts are stored in `src/prompts.yaml` and loaded at import time, keeping prompt text out of Python source. |
| `python-dotenv` | Env var loading | Loads `.env` into `os.environ` at startup. |

---

## Key Design Decisions

The full decision log is in [`docs/adr/`](docs/adr/). Key choices:

- **Docling over PyMuPDF / pdfplumber** — the only option with chart support; GPT-4o vision describes each chart on first parse, result cached to JSON. ([ADR-001](docs/adr/ADR-001-docling-pdf-parser.md))
- **Page-scoped extraction context** — Parts 1 and 2 pass only the relevant pages to the model, reducing noise and token cost. ([ADR-002](docs/adr/ADR-002-page-markers-in-extraction-context.md))
- **"Latest Actual" = Actual FY2022** — the question asks for "Latest Actual Fiscal Position"; the report labels one column simply "Actual", which corresponds to FY2022 in this document. We extract that column as the canonical answer to the ambiguous prompt. ([ADR-003](docs/adr/ADR-003-latest-actual-fiscal-position-column.md))
- **Operating revenue subcategories included** — sub-items of "Other Taxes" (e.g. Foreign Worker Levy) are listed separately in the source text and are included in the extracted list. ([ADR-004](docs/adr/ADR-004-operating-revenue-subcategories-included.md))
- **dateutil best-effort parsing** — partial and ambiguous date strings are accepted as-is from dateutil rather than enforcing strict formats. ([ADR-005](docs/adr/ADR-005-date-parsing-edge-cases.md))
- **H1-only chunking with table-aware paragraph grouping** — the PDF's markdown uses only H1 headings, so H1 splits are used to produce ~60 section chunks. Sections containing large tables are further split by grouping table rows with their preceding paragraph to avoid oversized chunks while preserving row context. ([ADR-006](docs/adr/ADR-006-chunking-strategy.md))
- **Single-shot agents with hard rejection** — agents answer in one pass; off-topic queries are rejected at the supervisor before any retrieval. ([ADR-007](docs/adr/ADR-007-single-shot-agent-design.md))

---

## Future Improvements

Given more time, the following would be the highest-leverage improvements:

1. **Self-correcting evaluation loop** — after each agent produces an answer, an evaluator node checks whether it actually answers the question. If not, the agent can decide to re-query with a refined search, ask for clarification, or declare that the document lacks sufficient context — rather than returning a confident but wrong answer.
2. **Automated evaluation dataset & judge** — generate a ground-truth Q&A dataset from the budget document, then run an LLM judge to score agent answers at scale. This enables systematic measurement of retrieval recall and answer quality across query types, and makes regressions detectable.
3. **ReAct loop for research agents** — replace the current single-shot answer with a Reason + Act loop: each agent can inspect retrieved chunks, decide if it needs to search again with a refined query, and iterate before committing to an answer.
4. **Citation handling for RAG** — the retrieved chunks and their source page numbers are currently only visible in log files. Surface them in the final answer so the user can trace every claim back to a specific page in the document.
5. **Hyperparameter tuning** — experiment with `top_k` (currently 4) and chunk overlap to find the retrieval settings that maximise recall without flooding the context window. Q3 is a concrete failure case where a higher `top_k` would likely recover the missing coverage context.
6. **Query decomposition** — for compound questions (e.g. "allocation *and* coverage"), have each agent generate multiple sub-queries and merge the retrieved context before answering, rather than relying on a single embedding match.

---

## Further Reading

| Document | Description |
|---|---|
| [Architecture](docs/architecture.md) | Full system diagram and per-part data flow |
| [Setup & Running](docs/setup.md) | Detailed setup, cache management, env vars |
| [Runbook](docs/runbook.md) | Run commands, log tuning, common failure fixes |
| [ADRs](docs/adr/) | Full decision records for all key choices |
| [Docling Parser](docs/docling.md) | Deep-dive on caching, chart description, prompt management |
| [MCP Datetime Server](docs/mcp.md) | Deep-dive on the FastMCP stdio server |
| [RAG Store](docs/rag.md) | Chunking strategy, ChromaDB embedding, search tool |
| [Multi-Agent Supervisor](docs/langgraph-supervisor.md) | LangGraph graph structure, routing logic, parallel fan-out |
