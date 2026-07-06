"""Ingestion pipeline orchestration."""

from __future__ import annotations

from pathlib import Path

from app.rag.ingestion.extractors import (
    extract_csv_document,
    extract_docx_document,
    extract_markdown_document,
    extract_pdf_document,
    extract_pptx_document,
    extract_text_document,
    extract_xlsx_document,
)
from app.rag.ingestion.models import ChunkRecord, IngestedDocument
from app.rag.ingestion.policy import split_with_policy
from app.rag.ingestion.quality import (
    is_informative_chunk,
    is_valid_chunk,
)


def load_ingested_document(path: Path) -> IngestedDocument | list[ChunkRecord]:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return extract_markdown_document(path)
    if suffix == ".txt":
        return extract_text_document(path)
    if suffix == ".pdf":
        return extract_pdf_document(path)
    if suffix == ".csv":
        return extract_csv_document(path)
    if suffix == ".pptx":
        return extract_pptx_document(path)
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
    structured_table_types = {"csv", "pptx", "xlsx"}
    filtered_chunks = []
    for chunk in chunks:
        file_type = str(chunk.metadata.get("file_type", "")).lower()
        min_len = 1 if file_type in structured_table_types else 100
        if is_valid_chunk(chunk.text, min_len=min_len) and is_informative_chunk(chunk.text):
            filtered_chunks.append(chunk)
    chunks = filtered_chunks

    return chunks


def chunks_to_dicts(chunks: list[ChunkRecord]) -> list[dict]:
    """Convert ChunkRecord list to dict list for add_to_index."""
    return [c.to_dict() for c in chunks]
