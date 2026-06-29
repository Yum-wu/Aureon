"""Ingestion pipeline orchestration."""

from __future__ import annotations

from pathlib import Path

from app.rag.ingestion.extractors import (
    extract_docx_document,
    extract_markdown_document,
    extract_pdf_document,
    extract_text_document,
    extract_xlsx_document,
)
from app.rag.ingestion.models import ChunkRecord, IngestedDocument
from app.rag.ingestion.policy import split_with_policy
from app.rag.ingestion.quality import (
    deduplicate_chunks,
    is_informative_chunk,
    is_valid_chunk,
)
from app.rag.ingestion.normalizer import normalize_text


def load_ingested_document(path: Path) -> IngestedDocument | list[ChunkRecord]:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return extract_markdown_document(path)
    if suffix == ".txt":
        return extract_text_document(path)
    if suffix == ".pdf":
        return extract_pdf_document(path)
    if suffix == ".docx":
        return extract_docx_document(path)
    if suffix == ".xlsx":
        return extract_xlsx_document(path)
    raise ValueError(f"Unsupported file type: {suffix}")


def build_chunks(path: Path) -> list[ChunkRecord]:
    loaded = load_ingested_document(path)
    if isinstance(loaded, IngestedDocument):
        chunks = split_with_policy(path.suffix.lower().lstrip("."), loaded)
    else:
        chunks = loaded

    # Quality gates
    chunks = [c for c in chunks if is_valid_chunk(c.text) and is_informative_chunk(c.text)]

    return chunks


def chunks_to_dicts(chunks: list[ChunkRecord]) -> list[dict]:
    """Convert ChunkRecord list to dict list for add_to_index."""
    return [c.to_dict() for c in chunks]
