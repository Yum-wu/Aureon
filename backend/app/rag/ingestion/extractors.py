"""File-type specific extraction helpers for ingestion."""

from __future__ import annotations

import re
from pathlib import Path

from app.rag.ingestion.models import ChunkRecord, IngestedDocument
from app.rag.ingestion.normalizer import normalize_text
from app.utils.lang_detect import detect_language as _detect_text_language


def parse_frontmatter(content: str) -> tuple[dict[str, object], str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if not match:
        return {}, content

    frontmatter_text = match.group(1)
    body = match.group(2).strip()

    metadata: dict[str, object] = {}
    for line in frontmatter_text.strip().split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if value.startswith("[") and value.endswith("]"):
                value = [v.strip().strip('"').strip("'") for v in value[1:-1].split(",")]
            metadata[key] = value
    return metadata, body


def extract_markdown_document(path: Path) -> IngestedDocument:
    content = path.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(content)
    lang = _detect_text_language(body[:500])
    return IngestedDocument(
        metadata={
            "source": path.name,
            "title": metadata.get("title", path.stem),
            "slug": metadata.get("slug", path.stem),
            "tags": metadata.get("tags", []),
            "category": metadata.get("category", ""),
            "filepath": str(path),
            "language": lang,
            "file_type": "md",
        },
        content=normalize_text(body),
    )


def extract_text_document(path: Path) -> IngestedDocument:
    content = normalize_text(path.read_text(encoding="utf-8"))
    return IngestedDocument(
        metadata={
            "source": path.name,
            "title": path.stem,
            "slug": path.stem,
            "tags": [],
            "category": "upload",
            "filepath": str(path),
            "language": _detect_text_language(content[:500]),
            "file_type": "txt",
        },
        content=content,
    )


def extract_pdf_document(path: Path) -> IngestedDocument:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text.strip())
    content = normalize_text("\n\n".join(pages))
    lang = _detect_text_language(content[:500]) if content else "en"
    return IngestedDocument(
        metadata={
            "source": path.name,
            "title": path.stem,
            "slug": path.stem,
            "tags": [],
            "category": "upload",
            "filepath": str(path),
            "language": lang,
            "file_type": "pdf",
        },
        content=content,
    )


def extract_docx_document(path: Path) -> list[ChunkRecord]:
    from docx import Document

    doc = Document(str(path))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    content = normalize_text("\n\n".join(paragraphs))
    lang = _detect_text_language(content[:500]) if content else "en"
    return [
        ChunkRecord(
            text=content,
            metadata={
                "source": path.name,
                "title": path.stem,
                "slug": path.stem,
                "tags": [],
                "category": "upload",
                "filepath": str(path),
                "language": lang,
                "file_type": "docx",
            },
        )
    ]


def extract_xlsx_document(path: Path) -> list[ChunkRecord]:
    from openpyxl import load_workbook

    wb = load_workbook(str(path), read_only=True, data_only=True)
    lines = []
    for ws in wb.worksheets:
        headers = []
        for row in ws.iter_rows(values_only=True):
            if not headers:
                headers = [str(h) if h is not None else f"col{i}" for i, h in enumerate(row)]
                continue
            parts = []
            for h, v in zip(headers, row):
                if v is not None:
                    parts.append(f"{h}: {v}")
            if parts:
                lines.append(", ".join(parts))
    wb.close()

    content = normalize_text("\n".join(lines))
    lang = _detect_text_language(content[:500]) if content else "en"
    return [
        ChunkRecord(
            text=content,
            metadata={
                "source": path.name,
                "title": path.stem,
                "slug": path.stem,
                "tags": [],
                "category": "upload",
                "filepath": str(path),
                "language": lang,
                "file_type": "xlsx",
            },
        )
    ]
