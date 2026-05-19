"""PDF parsing utilities using Docling with two-level caching."""

from __future__ import annotations

import os
import time
from pathlib import Path

import yaml

from docling.datamodel.base_models import InputFormat
from docling.datamodel.document import DoclingDocument, PictureItem, TableItem
from docling.datamodel.pipeline_options import PdfPipelineOptions, PictureDescriptionApiOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc.document import ImageRefMode
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

_PROMPTS = yaml.safe_load((Path(__file__).parent.parent / "prompts.yaml").read_text())

# PictureDescriptionApiOptions calls any OpenAI-compatible chat completions endpoint.
# generate_picture_images must be True so that the image bytes are retained in the
# DoclingDocument for GPT-4o to receive — without it, Docling discards chart images
# after layout detection and has nothing to describe.
_PDF_PIPELINE_OPTIONS = PdfPipelineOptions(
    generate_picture_images=True,
    do_picture_description=True,
    enable_remote_services=True,  # required to allow the OpenAI API call
    picture_description_options=PictureDescriptionApiOptions(
        url="https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '')}"},
        params={"model": "gpt-4o"},
        prompt=_PROMPTS["parser"]["picture_description"],
        timeout=60.0,
    ),
)

# Module-level cache so the DoclingDocument survives for the duration of the process.
# All three part scripts import this module, so a single parse serves all of them.
_DOCUMENT_CACHE: dict[str, DoclingDocument] = {}


def _get_document(pdf_path: Path, cache_dir: Path) -> DoclingDocument:
    """Return DoclingDocument for pdf_path.

    Cache order:
      1. In-memory dict  — instant; survives as long as the process runs
      2. JSON disk cache — ~3–4s; survives across separate process runs
      3. Full Docling parse — ~60–100s on first run + GPT-4o call per chart
    """
    # resolve() normalises relative paths so the same file isn't cached under two keys
    cache_key = str(pdf_path.resolve())

    # --- Level 1: in-memory ---
    if cache_key in _DOCUMENT_CACHE:
        logger.debug("DoclingDocument cache hit (memory): {}", pdf_path.name)
        return _DOCUMENT_CACHE[cache_key]

    cache_dir.mkdir(parents=True, exist_ok=True)
    json_cache = cache_dir / f"{pdf_path.stem}.json"

    # --- Level 2: JSON disk ---
    # DoclingDocument is a Pydantic model, so model_dump_json / model_validate_json
    # round-trips it without any custom serialisation logic.
    if json_cache.exists():
        logger.debug("DoclingDocument cache hit (disk): {}", json_cache.name)
        doc = DoclingDocument.model_validate_json(json_cache.read_text(encoding="utf-8"))
        _DOCUMENT_CACHE[cache_key] = doc
        return doc

    # --- Level 3: full parse ---
    logger.info("Parsing {} with Docling (first run: ~60–100s + GPT-4o per chart)…", pdf_path.name)
    start = time.perf_counter()
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=_PDF_PIPELINE_OPTIONS)}
    )
    doc = converter.convert(str(pdf_path)).document
    elapsed = time.perf_counter() - start
    logger.info("Docling parse complete in {:.1f}s", elapsed)

    json_cache.write_text(doc.model_dump_json(), encoding="utf-8")
    _DOCUMENT_CACHE[cache_key] = doc
    return doc


def parse_pdf(pdf_path: Path, cache_dir: Path) -> str:
    """Return full document markdown. Caches result to cache_dir/<stem>.md."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    md_cache = cache_dir / f"{pdf_path.stem}.md"

    # Check the markdown file before loading the DoclingDocument — this keeps the
    # second-call return time under 1ms without touching the JSON cache at all.
    if md_cache.exists():
        logger.debug("Markdown cache hit: {}", md_cache.name)
        return md_cache.read_text(encoding="utf-8")

    doc = _get_document(pdf_path, cache_dir)
    markdown = doc.export_to_markdown()
    md_cache.write_text(markdown, encoding="utf-8")
    return markdown


def parse_pages(pdf_path: Path, page_nums: list[int], cache_dir: Path) -> str:
    """Return concatenated markdown for specific 1-indexed pages.

    Uses the DoclingDocument directly instead of slicing the markdown string,
    because Docling's item-level prov.page_no is reliable whereas markdown page
    markers are fragile and differ across Docling versions.
    """
    doc = _get_document(pdf_path, cache_dir)
    page_set = set(page_nums)
    parts: list[str] = []

    for item, _level in doc.iterate_items():
        if not item.prov:
            continue

        # Each item carries provenance (page number, bounding box) for every page it touches.
        # An item is included if any of its pages overlap with the requested set.
        item_pages = {p.page_no for p in item.prov}
        if not item_pages & page_set:
            continue

        try:
            if isinstance(item, TableItem):
                # Pass doc so Docling can resolve cross-references within the table
                md = item.export_to_markdown(doc)
                if md:
                    parts.append(md)
            elif isinstance(item, PictureItem):
                # PLACEHOLDER mode outputs the GPT-4o description text instead of
                # embedding the raw base64 image, which is what an LLM text input needs.
                md = item.export_to_markdown(doc, image_mode=ImageRefMode.PLACEHOLDER)
                if md:
                    parts.append(md)
            elif hasattr(item, "text") and item.text:
                parts.append(item.text)
        except Exception as exc:
            # A corrupt or unrecognised element shouldn't abort the whole extraction.
            logger.warning("Skipping item on page(s) {}: {}", sorted(item_pages), exc)

    return "\n\n".join(parts)


if __name__ == "__main__":
    import sys

    pdf = Path("data/fy2024_analysis_of_revenue_and_expenditure.pdf")
    cache = Path("data/cache")

    logger.info("Running parser smoke test…")

    markdown = parse_pdf(pdf, cache)
    logger.info("parse_pdf: {:,} chars", len(markdown))

    page_nums = [int(p) for p in sys.argv[1:]] if sys.argv[1:] else [5]
    snippet = parse_pages(pdf, page_nums, cache)
    logger.info("parse_pages({}) returned {:,} chars", page_nums, len(snippet))
    print(snippet)
