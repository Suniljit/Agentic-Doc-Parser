# ChromaDB RAG Store

## Summary
Chunk the Docling markdown into semantically meaningful sections, embed with `text-embedding-3-small`, persist in ChromaDB, and expose a `search_document` LangChain tool that Part 3 agents will call.

## Branch name
`feat/chromadb-rag-store`

## What to build
A module `src/utils/rag.py` with two public functions: `build_store()` and `get_retriever_tool()`.

**Layers touched:** `src/utils/rag.py · data/cache/chroma/`

---

### Chunking strategy
Split the Docling markdown by section headings (`# `) to preserve semantic coherence — the Docling output uses only H1 headings throughout (see ADR-006). Apply a secondary fixed-size split (1000 chars, 100 char overlap) to all chunks to bound chunk size. Each chunk retains its heading as metadata (`section`); the heading is surfaced to the LLM as a `[section]` prefix in `search_document` results rather than embedded in the chunk body.

```python
from langchain_text_splitters import MarkdownHeaderTextSplitter
```

---

### Embedding & storage
```python
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
vectorstore = Chroma(
    collection_name="fy2024",
    embedding_function=embeddings,
    persist_directory="data/cache/chroma"
)
```

- `build_store(markdown: str, persist_dir: Path) -> Chroma` — builds and persists the store; skips re-building if `persist_dir` already exists
- Log chunk count and embedding duration at INFO level

---

### LangChain tool
```python
from langchain_core.tools import tool

@tool
def search_document(query: str) -> str:
    """Search the FY2024 budget document for information relevant to the query."""
    docs = retriever.invoke(query)
    return "\n\n".join(f"[{d.metadata.get('section','?')}]\n{d.page_content}" for d in docs)
```

- `get_retriever_tool(vectorstore: Chroma, k: int = 4) -> Tool` — returns the bound `search_document` tool
- Retriever uses `k=4` by default

## Acceptance criteria
- [ ] `build_store()` completes and persists to `data/cache/chroma/`
- [ ] Second call to `build_store()` detects existing store and skips re-embedding (fast path)
- [ ] `search_document("Corporate Income Tax")` returns at least one chunk containing relevant text
- [ ] `search_document("Future Energy Fund")` returns at least one chunk about energy expenditure
- [ ] Each returned chunk includes a `section` metadata label
- [ ] Chunk count and embedding duration logged at INFO level
- [ ] No `print` statements; all logging via loguru

## Implementation notes
- `data/cache/chroma/` must be added to `.gitignore`
- The `Chroma` persist directory check: if `os.path.exists(persist_dir)` and it's non-empty, load existing store instead of rebuilding
- `langchain-chroma` is a separate package from `chromadb` — both needed in `pyproject.toml`

## Feature brief coverage
**Functional requirements:** FR-5
**Non-functional requirements:** NFR-1, NFR-2

## Blocked by
- #02 — Docling PDF Parser

## Status
`todo`
