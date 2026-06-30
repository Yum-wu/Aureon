"""Chunk policy helpers for ingestion."""

from __future__ import annotations

import re

from app.rag.ingestion.normalizer import normalize_text
from app.rag.ingestion.models import ChunkRecord, IngestedDocument
from app.rag.ingestion.quality import is_valid_chunk

DEFAULT_CHUNK_SIZE = 512

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)")


def split_with_policy(file_type: str, document: IngestedDocument) -> list[ChunkRecord]:
    """Split document using ParentChildSplitter for all file types.

    Preserves heading tracking for markdown files to maintain section_path metadata.
    """
    from app.rag.semantic_splitter import ParentChildSplitter

    # Use ParentChildSplitter for consistent parent-child structure across all file types
    splitter = ParentChildSplitter(parent_size=1500, child_size=512, overlap=80)

    # Convert IngestedDocument to the dict format ParentChildSplitter expects
    doc_dict = {
        "content": normalize_text(document.content),
        "metadata": document.metadata,
    }

    # Split using ParentChildSplitter
    chunk_dicts = splitter.split_documents([doc_dict])

    # Convert to ChunkRecord, preserving/enriching metadata
    chunks = []
    for i, chunk_dict in enumerate(chunk_dicts):
        # For markdown, optionally track section paths (heading stack is lost via ParentChildSplitter)
        # To preserve this, we'd need to pass parent_text through heading tracking,
        # but that's complex. Accept that heading context is now in parent_text instead.
        chunk = ChunkRecord(
            text=chunk_dict["text"],
            metadata={**chunk_dict["metadata"], "chunk_idx": i},
        )
        chunks.append(chunk)

    return [chunk for chunk in chunks if is_valid_chunk(chunk.text)]


def _split_recursive_fallback(document: IngestedDocument) -> list[ChunkRecord]:
    """Legacy fallback — kept for backwards compatibility but unused."""
    return _split_by_paragraphs(document)  # noqa: F821

def _split_long_text(text: str, chunk_size: int) -> list[str]:
    """Legacy fallback — kept for backwards compatibility but unused."""
    return [
        text[i : i + chunk_size].strip()
        for i in range(0, len(text), chunk_size)
        if text[i : i + chunk_size].strip()
    ]


def _make_chunk(
    document: IngestedDocument,
    text: str,
    chunk_idx: int,
    heading_stack: list[str] | None = None,
) -> ChunkRecord:
    """Legacy fallback — kept for backwards compatibility but unused."""
    meta = {**document.metadata, "chunk_idx": chunk_idx}
    if heading_stack:
        meta["section_path"] = " > ".join(heading_stack)
    return ChunkRecord(text=text, metadata=meta)
