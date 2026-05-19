# Project Documentation Index
> Run `/doc-auditor` to keep this current.

## Architecture & Design
| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | System overview, component diagram, data flow for all three parts |
| [Feature Brief](specs/feature-brief.md) | Full design spec — goals, requirements, design decisions |
| [Docling Parser](docs/docling.md) | Deep-dive on parser.py: caching, GPT-4o chart description, prompt management |
| [MCP Datetime Server](docs/mcp.md) | Deep-dive on mcp/datetime_server.py: normalize_date tool, stdio transport, standalone usage |
| [RAG Store](docs/rag.md) | Deep-dive on rag.py: chunking strategy, table-aware paragraph grouping, ChromaDB embedding, search_document tool |
| [Multi-Agent Supervisor](docs/langgraph-supervisor.md) | Deep-dive on part3_agent.py: graph structure, node behaviour, routing logic, parallel fan-out, and usage |

## Architecture Decision Records (ADRs)
| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [ADR-001](docs/adr/ADR-001-docling-pdf-parser.md) | Docling for PDF Parsing | Accepted | 2026-05-18 |
| [ADR-002](docs/adr/ADR-002-page-markers-in-extraction-context.md) | Selective Page Extraction with Page Markers | Accepted | 2026-05-19 |
| [ADR-003](docs/adr/ADR-003-latest-actual-fiscal-position-column.md) | "Latest Actual" Fiscal Position Maps to Actual FY2022 | Accepted | 2026-05-19 |
| [ADR-004](docs/adr/ADR-004-operating-revenue-subcategories-included.md) | Operating Revenue Subcategories Included in Tax List | Accepted | 2026-05-19 |
| [ADR-005](docs/adr/ADR-005-date-parsing-edge-cases.md) | Accept dateutil Best-Effort Parsing for Partial and Ambiguous Dates | Accepted | 2026-05-19 |
| [ADR-006](docs/adr/ADR-006-chunking-strategy.md) | H1-Only Chunking Strategy for ChromaDB RAG Store | Accepted | 2026-05-19 |
| [ADR-007](docs/adr/ADR-007-single-shot-agent-design.md) | Single-Shot Agent Design and Hard Rejection for Off-Topic Queries | Accepted | 2026-05-19 |

## Operations & Runbooks
| Document | Description |
|----------|-------------|
| [Setup & Running](docs/setup.md) | Install, env vars, how to run each part |
| [Runbook](docs/runbook.md) | Run commands, cache management, log tuning, common failure fixes |

## Onboarding & Guides
| Document | Description |
|----------|-------------|
| [Tickets](specs/tickets/) | Per-feature work breakdown |
| [Plans](specs/plans/) | Per-ticket implementation plans |
