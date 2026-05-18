# System Architecture

> Agentic Document Parser — FY2024 Singapore Budget PDF pipeline.

## Overview

Three self-contained scripts share a common foundation (OpenAI client, Docling parser). Each part builds on the previous one's output but runs independently via `uv run`.

```
┌─────────────────────────────────────────────────────────┐
│                    SHARED FOUNDATION                     │
│                                                         │
│  src/utils/llm.py    — singleton OpenAI client (gpt-4o) │
│  src/utils/parser.py — Docling PDF → markdown (cached)  │
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
│Pydantic│  │OpenAI│         │  │ (GPT-4o routing)        │
│ model  │  │fn-call         │  │   ┌──────┴──────┐       │
│ output │  │      │         │  │   ▼             ▼       │
└────────┘  │      │         │  │ Revenue    Expenditure  │
            │ GPT-4o reasons │  │  Agent       Agent      │
            │ over dates     │  │ (RAG tool)  (RAG tool)  │
            └────────────────┘  └─────────────────────────┘
```

## Part Breakdown

### Part 1 — Structured Extraction (`src/part1_extraction.py`)
Single GPT-4o call extracts five typed fields from the PDF and validates them against a Pydantic model.

```
PDF ──► Docling ──► markdown ──► page slice (pp. 5,6,8,20)
                                      │
                               GPT-4o call
                               (json_object mode)
                                      │
                               ExtractionResult
                               (Pydantic validated)
```

### Part 2 — Tool Calling & Date Reasoning (`src/part2_tool_calling.py`)
GPT-4o extracts dates via function calling, dispatching each to a FastMCP server over stdio. A second call classifies dates relative to `2024-01-01`.

```
PDF ──► Docling ──► markdown ──► page slice (pp. 1, 36)
                                      │
                               GPT-4o call (with tools)
                               ◄── tool_calls ──►
                               MCP client (stdio)
                               ──► mcp/datetime_server.py
                               ◄── ISO date string
                                      │
                               GPT-4o call #2
                               (classify: Expired/Upcoming/Ongoing)
                                      │
                               JSON output
```

### Part 3 — Multi-Agent Supervisor (`src/part3_agent.py`)
LangGraph graph with typed state routes queries to specialist agents via GPT-4o reasoning. Each agent retrieves context from ChromaDB before answering.

```
query
  │
  ▼
supervisor node (GPT-4o)
  │ routes to: revenue | expenditure | both
  ├──► revenue_agent ──► ChromaDB search ──► GPT-4o answer
  └──► expenditure_agent ──► ChromaDB search ──► GPT-4o answer
          │                       │
          └───────────────────────┘
                      │
               synthesizer node (GPT-4o)
                      │
               final_answer
```

## Directory Structure

```
Agentic-Doc-Parser/
├── pyproject.toml          — all deps, single source of truth
├── .env.example            — required env vars (copy to .env)
├── data/
│   ├── fy2024_*.pdf        — source document
│   └── cache/              — Docling parse cache (gitignored)
├── docs/                   — this folder
├── mcp/
│   └── datetime_server.py  — FastMCP stdio server (Part 2)
├── specs/
│   ├── feature-brief.md    — full design spec
│   ├── plans/              — per-ticket implementation plans
│   └── tickets/            — work breakdown
└── src/
    ├── utils/
    │   ├── llm.py          — OpenAI client singleton + loguru
    │   └── parser.py       — Docling PDF parser (ticket 02)
    ├── part1_extraction.py
    ├── part2_tool_calling.py
    └── part3_agent.py
```

## Related
- [Feature Brief](../specs/feature-brief.md)
- [Setup Guide](setup.md)
