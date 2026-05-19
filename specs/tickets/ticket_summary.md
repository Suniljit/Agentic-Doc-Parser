# Agentic Document Parser — Ticket Summary

| # | Ticket | Type | Blocked by | Status |
|---|--------|------|------------|--------|
| 01 | [Project Scaffolding](01-project-scaffolding.md) | AFK | — | `done` |
| 02 | [Docling PDF Parser](02-docling-pdf-parser.md) | AFK | #01 | `done` |
| 03 | [Part 1: Structured Extraction](03-part1-structured-extraction.md) | AFK | #02 | `done` |
| 04 | [FastMCP Datetime Server](04-fastmcp-datetime-server.md) | AFK | #01 | `todo` |
| 05 | [Part 2: Tool-Calling & Date Reasoning](05-part2-tool-calling-date-reasoning.md) | AFK | #02, #04 | `todo` |
| 06 | [ChromaDB RAG Store](06-chromadb-rag-store.md) | AFK | #02 | `todo` |
| 07 | [LangGraph Multi-Agent Supervisor](07-langgraph-multi-agent-supervisor.md) | AFK | #06 | `todo` |
| 08 | [README & Documentation](08-readme-documentation.md) | AFK | #03, #05, #07 | `todo` |

## Execution order

```
Wave 1 — start immediately:
  #01 Project Scaffolding

Wave 2 — after #01 (run in parallel):
  #02 Docling PDF Parser
  #04 FastMCP Datetime Server

Wave 3 — after #02 (run in parallel):
  #03 Part 1: Structured Extraction
  #05 Part 2: Tool-Calling & Date Reasoning  (also needs #04)
  #06 ChromaDB RAG Store

Wave 4 — after #06:
  #07 LangGraph Multi-Agent Supervisor

Wave 5 — after #03 + #05 + #07:
  #08 README & Documentation
```
