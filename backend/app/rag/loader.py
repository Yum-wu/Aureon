"""
Document loader for RAG system.
Loads Markdown blog posts, parses frontmatter, and splits into chunks.
"""

from typing import List, Dict, Any
from pathlib import Path

import structlog

from app.rag.ingestion.extractors import (
    extract_csv_document,
    extract_docx_document,
    extract_markdown_document,
    extract_pdf_document,
    extract_pptx_document,
    parse_frontmatter,
    extract_text_document,
    extract_xlsx_document,
)
from app.utils.lang_detect import detect_language as _detect_text_language

logger = structlog.get_logger()


def _require_chunks(chunks: list, file_type: str) -> list:
    if not chunks:
        if file_type == "csv":
            raise ValueError("CSV contains no header row or extractable text")
        raise ValueError(f"{file_type.upper()} contains no extractable text")
    return chunks


def detect_doc_language(content: str, frontmatter_lang: str = None) -> str:
    """Detect document language, preferring frontmatter over auto-detection.

    Uses the shared lang_detect utility for consistent detection logic.
    """
    if frontmatter_lang in ("zh", "en"):
        return frontmatter_lang
    return _detect_text_language(content[:500])


def load_single_document(filepath: str) -> Dict[str, Any]:
    """Load a single document and return {metadata, content}.

    Supports: .md, .txt, .pdf, .docx, .xlsx, .csv, .pptx
    Args:
        filepath: Absolute path to file.
    Returns:
        dict with keys: metadata, content
    """
    fpath = Path(filepath)
    suffix = fpath.suffix.lower()

    if suffix == ".md":
        doc = extract_markdown_document(fpath)
        metadata = dict(doc.metadata)
        metadata.pop("file_type", None)
        return {
            "metadata": {**metadata, "uploaded": True},
            "content": doc.content,
        }
    elif suffix == ".txt":
        doc = extract_text_document(fpath)
        metadata = dict(doc.metadata)
        metadata.pop("file_type", None)
        return {"metadata": {**metadata, "uploaded": True}, "content": doc.content}
    elif suffix == ".pdf":
        doc = extract_pdf_document(fpath)
        metadata = dict(doc.metadata)
        metadata.pop("file_type", None)
        return {"metadata": {**metadata, "uploaded": True}, "content": doc.content}
    elif suffix == ".docx":
        chunks = _require_chunks(extract_docx_document(fpath), "docx")
        metadata = dict(chunks[0].metadata)
        metadata.pop("file_type", None)
        return {"metadata": {**metadata, "uploaded": True}, "content": chunks[0].text}
    elif suffix == ".xlsx":
        chunks = _require_chunks(extract_xlsx_document(fpath), "xlsx")
        metadata = dict(chunks[0].metadata)
        metadata.pop("file_type", None)
        return {"metadata": {**metadata, "uploaded": True}, "content": chunks[0].text}
    elif suffix == ".csv":
        chunks = _require_chunks(extract_csv_document(fpath), "csv")
        return {"metadata": {**chunks[0].metadata, "uploaded": True}, "content": chunks[0].text}
    elif suffix == ".pptx":
        chunks = _require_chunks(extract_pptx_document(fpath), "pptx")
        metadata = dict(chunks[0].metadata)
        metadata.pop("file_type", None)
        return {
            "metadata": {**metadata, "uploaded": True, "file_type": "pptx"},
            "content": "\n\n".join(chunk.text for chunk in chunks),
        }
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def load_markdown_files(articles_dir: str) -> List[Dict[str, Any]]:
    """Load all Markdown files from directory. Return list of {metadata, content, filepath}."""
    docs = []
    path = Path(articles_dir)
    if not path.exists():
        logger.warning("Articles dir not found: %s", articles_dir)
        return docs

    # 跳过 expansion 目录（扩展文档，等 500 文档扩容时使用）
    _EXCLUDE_DIRS = {"expansion", "uploads"}

    for fpath in sorted(path.rglob("*.md")):
        # 跳过排除目录中的文件
        if any(part in _EXCLUDE_DIRS for part in fpath.parts):
            continue
        content = fpath.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(content)
        lang = detect_doc_language(body, metadata.get("lang"))
        doc = {
            "metadata": {
                "source": fpath.name,
                "title": metadata.get("title", fpath.stem),
                "slug": metadata.get("slug", fpath.stem),
                "tags": metadata.get("tags", []),
                "category": metadata.get("category", ""),
                "filepath": str(fpath),
                "language": lang,
            },
            "content": body,
        }
        docs.append(doc)

    logger.info("Loaded %d documents from %s", len(docs), articles_dir)
    return docs


# ── Legacy loader wrappers (used by tests) ──


def load_pdf(filepath: str) -> Dict[str, Any]:
    """Load a PDF file and return {metadata, content}.

    Thin wrapper around extract_pdf_document for backward compatibility.
    """
    doc = extract_pdf_document(Path(filepath))
    return {"metadata": dict(doc.metadata), "content": doc.content}


def load_docx(filepath: str) -> Dict[str, Any]:
    """Load a DOCX file and return {metadata, content}.

    Thin wrapper around extract_docx_document for backward compatibility.
    """
    chunks = _require_chunks(extract_docx_document(Path(filepath)), "docx")
    return {"metadata": dict(chunks[0].metadata), "content": chunks[0].text}


def load_excel(filepath: str) -> Dict[str, Any]:
    """Load an XLSX file and return {metadata, content}.

    Thin wrapper around extract_xlsx_document for backward compatibility.
    """
    chunks = _require_chunks(extract_xlsx_document(Path(filepath)), "xlsx")
    return {"metadata": dict(chunks[0].metadata), "content": chunks[0].text}


def load_csv(filepath: str) -> Dict[str, Any]:
    """Load a CSV file and return {metadata, content}.

    Thin wrapper around extract_csv_document for backward compatibility.
    """
    chunks = _require_chunks(extract_csv_document(Path(filepath)), "csv")
    return {"metadata": dict(chunks[0].metadata), "content": chunks[0].text}


def load_pptx(filepath: str) -> Dict[str, Any]:
    """Load a PPTX file and return {metadata, content}.

    Thin wrapper around extract_pptx_document for backward compatibility.
    """
    chunks = _require_chunks(extract_pptx_document(Path(filepath)), "pptx")
    return {
        "metadata": dict(chunks[0].metadata),
        "content": "\n\n".join(chunk.text for chunk in chunks),
    }
