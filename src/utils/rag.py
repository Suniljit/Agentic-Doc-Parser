"""RAG store utilities: chunking, embedding, and LangChain retrieval tool."""

from __future__ import annotations

import time
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter
from loguru import logger

load_dotenv()


_H1_SPLITTER = MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "section")])


def _is_table(text: str) -> bool:
    return any(line.startswith("|") for line in text.splitlines())


def _chunk_section(doc: Document) -> list[Document]:
    """Split a section Document into chunks.

    Prose-only sections are returned as a single chunk. Sections containing
    tables are split so each table is atomic (title + rows + footnotes in one
    chunk); any prose that is not adjacent to a table is kept together as one
    additional chunk.
    """
    # Split on double-newlines, which often separate paragraphs and/or tables in the markdown.
    paragraphs = [p.strip() for p in doc.page_content.split("  \n") if p.strip()]

    metadata = doc.metadata  # contains {"section": "Heading Text"}

    if not any(_is_table(p) for p in paragraphs):
        return [Document(page_content=doc.page_content.strip(), metadata=metadata)]

    result: list[Document] = []
    pending_prose: list[str] = []
    i = 0
    n = len(paragraphs)

    while i < n:
        para = paragraphs[i]

        if _is_table(para):
            group: list[str] = []

            # Use the last pending prose paragraph as the table title; flush
            # any earlier prose paragraphs as a single chunk before the table.
            if pending_prose:
                group.append(pending_prose.pop())
                if pending_prose:
                    result.append(
                        Document(page_content="\n\n".join(pending_prose), metadata=metadata)
                    )
                    pending_prose = []

            group.append(para)
            i += 1

            # Absorb following footnote/note paragraphs. Stop when we reach a
            # prose paragraph immediately followed by a table — that paragraph
            # is the next table's title, not a footnote.
            while i < n and not _is_table(paragraphs[i]):
                if i + 1 < n and _is_table(
                    paragraphs[i + 1]
                ):  # next para is a table, so current para is likely a title, not a footnote
                    break
                group.append(paragraphs[i])
                i += 1

            result.append(Document(page_content="\n\n".join(group), metadata=metadata))
        else:
            pending_prose.append(para)  # current paragraph is prose.
            i += 1

    # Flush any remaining prose after the last table.
    if pending_prose:
        result.append(Document(page_content="\n\n".join(pending_prose), metadata=metadata))

    return result


def build_store(markdown: str, persist_dir: Path) -> Chroma:
    """Chunk, embed, and persist the markdown in ChromaDB.

    Skips re-embedding if persist_dir already exists and is non-empty.
    """
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    # Check for existing ChromaDB store
    if persist_dir.exists() and any(persist_dir.iterdir()):
        logger.info("ChromaDB store found at {} — loading existing", persist_dir)
        return Chroma(
            collection_name="fy2024",
            embedding_function=embeddings,
            persist_directory=str(persist_dir),
        )

    # No existing store found — build a new one.
    logger.info("Building ChromaDB store…")

    section_docs = _H1_SPLITTER.split_text(markdown)
    chunks: list[Document] = []
    for section in section_docs:
        chunks.extend(_chunk_section(section))
    chunks = [c for c in chunks if c.page_content.strip()]

    logger.info("Embedding {} chunks…", len(chunks))
    start = time.perf_counter()

    persist_dir.mkdir(parents=True, exist_ok=True)
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name="fy2024",
        persist_directory=str(persist_dir),
    )

    elapsed = time.perf_counter() - start
    logger.info("Embedded {} chunks in {:.1f}s", len(chunks), elapsed)

    return vectorstore


def get_retriever_tool(vectorstore: Chroma, k: int = 4):
    """Return a search_document LangChain tool bound to vectorstore."""
    retriever = vectorstore.as_retriever(search_kwargs={"k": k})

    @tool
    def search_document(query: str) -> str:
        """Search the FY2024 budget document for information relevant to the query."""
        docs = retriever.invoke(query)
        return "\n\n".join(f"[{d.metadata.get('section', '?')}]\n{d.page_content}" for d in docs)

    return search_document
