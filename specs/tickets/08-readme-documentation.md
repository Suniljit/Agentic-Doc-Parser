# README & Documentation

## Summary
Write the project README covering setup, per-part execution, design decisions, and library justifications — the final deliverable required by the assessment submission checklist.

## Branch name
`feat/readme`

## What to build
A `README.md` at the repo root that a reviewer can follow from clone to running all three parts.

**Layers touched:** `README.md`

---

### Required sections (per assessment spec)

1. **Overview** — what the project does, the three-part structure
2. **Setup**
   - Prerequisites: Python 3.13, `uv`, OpenAI API key
   - Clone, create venv, install deps: `uv venv .venv --python 3.13 && uv sync`
   - Copy `.env.example` to `.env` and fill in `OPENAI_API_KEY`
3. **Running each part**
   ```bash
   uv run python src/part1_extraction.py   # Part 1
   uv run python src/part2_tool_calling.py # Part 2
   uv run python src/part3_agent.py        # Part 3
   ```
4. **System design** — architecture diagram (copy from feature brief), explanation of data flow
5. **Library & dependency justification** — for each key library, one sentence on why it was chosen over alternatives:
   - Docling vs PyMuPDF / pdfplumber
   - FastMCP for MCP server
   - ChromaDB + LangChain for RAG
   - LangGraph for multi-agent orchestration
   - loguru for structured logging
6. **Design decisions** — summarise the key choices from the feature brief (LLM provider, single-call extraction, LLM-based routing, dynamic RAG vs pre-chunked context)
7. **Assumptions** — any assumptions made where the spec was silent
8. **Known limitations** — out-of-scope items that would matter in production

## Acceptance criteria
- [ ] README exists at repo root
- [ ] A reviewer can follow Setup instructions on a clean machine to get a working environment
- [ ] All three `uv run` commands are present and correct
- [ ] Each key library is justified in one or more sentences
- [ ] Architecture diagram is present (ASCII)
- [ ] Design decisions section references tradeoffs (not just choices)
- [ ] Assumptions section is present and non-empty

## Implementation notes
- Write this last — after all three parts are working — so the run commands and outputs are accurate
- Keep it concise: reviewers skim READMEs; bullet points over paragraphs where possible
- Do not commit API keys to the README; reference `.env.example` only

## Feature brief coverage
**Functional requirements:** FR-1 through FR-8 (documentation of all)
**Non-functional requirements:** NFR-3, NFR-4

## Blocked by
- #03 — Part 1: Structured Extraction
- #05 — Part 2: Tool-Calling & Date Reasoning
- #07 — LangGraph Multi-Agent Supervisor

## Status
`todo`
