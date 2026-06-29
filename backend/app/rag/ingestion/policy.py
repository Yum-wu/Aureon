"""Chunk policy helpers for ingestion."""

from __future__ import annotations

import re

from app.rag.ingestion.normalizer import normalize_text
from app.rag.ingestion.models import ChunkRecord, IngestedDocument
from app.rag.ingestion.quality import is_valid_chunk

DEFAULT_CHUNK_SIZE = 512

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)")


def split_with_policy(file_type: str, document: IngestedDocument) -> list[ChunkRecord]:
    if file_type == "md":
        return _split_by_paragraphs(document, track_headings=True)
    if file_type == "txt":
        return _split_by_paragraphs(document)
    if file_type == "pdf":
        return _split_by_paragraphs(document)
    return _split_recursive_fallback(document)


def _track_section_path(paragraph: str, stack: list[str]) -> None:
    """Update heading stack from a paragraph.

    - # Title           → stack = ["Title"]
    - ## Sub            → stack = ["Title", "Sub"]
    - ### Sub3          → stack = ["Title", "Sub", "Sub3"]
    - back to ## New    → stack = ["Title", "New"]
    - non-heading       → stack unchanged
    """
    m = _HEADING_RE.match(paragraph)
    if not m:
        return
    level = len(m.group(1))
    heading_text = m.group(2).strip()
    # Pop deeper headings, replace at current level
    stack[:] = stack[: level - 1] + [heading_text]


def _split_by_paragraphs(
    document: IngestedDocument,
    *,
    track_headings: bool = False,
) -> list[ChunkRecord]:
    text = normalize_text(document.content)
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks: list[ChunkRecord] = []
    buffer = ""
    heading_stack: list[str] = []

    for paragraph in paragraphs:
        if track_headings:
            _track_section_path(paragraph, heading_stack)

        candidate = f"{buffer}\n\n{paragraph}".strip() if buffer else paragraph
        if len(candidate) <= DEFAULT_CHUNK_SIZE:
            buffer = candidate
            continue

        if buffer:
            chunks.append(_make_chunk(document, buffer, len(chunks), heading_stack))
            buffer = ""

        if len(paragraph) <= DEFAULT_CHUNK_SIZE:
            buffer = paragraph
        else:
            for part in _split_long_text(paragraph, DEFAULT_CHUNK_SIZE):
                chunks.append(_make_chunk(document, part, len(chunks), heading_stack))

    if buffer:
        chunks.append(_make_chunk(document, buffer, len(chunks), heading_stack))

    return [chunk for chunk in chunks if is_valid_chunk(chunk.text)]


def _split_recursive_fallback(document: IngestedDocument) -> list[ChunkRecord]:
    return _split_by_paragraphs(document)


def _split_long_text(text: str, chunk_size: int) -> list[str]:
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
    meta = {**document.metadata, "chunk_idx": chunk_idx}
    if heading_stack:
        meta["section_path"] = " > ".join(heading_stack)
    return ChunkRecord(text=text, metadata=meta)
