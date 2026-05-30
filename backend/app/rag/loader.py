"""
Document loader for RAG system.
Loads Markdown blog posts, parses frontmatter, and splits into chunks.
"""

import os
import re
from typing import List, Dict, Any
from pathlib import Path

from app.utils.lang_detect import detect_language as _detect_text_language


def detect_doc_language(content: str, frontmatter_lang: str = None) -> str:
    """Detect document language, preferring frontmatter over auto-detection.

    Uses the shared lang_detect utility for consistent detection logic.
    """
    if frontmatter_lang in ("zh", "en"):
        return frontmatter_lang
    return _detect_text_language(content[:500])


def parse_frontmatter(content: str) -> tuple[Dict[str, Any], str]:
    """Parse YAML frontmatter from Markdown content. Return (metadata, body)."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if not match:
        return {}, content

    frontmatter_text = match.group(1)
    body = match.group(2).strip()

    metadata = {}
    for line in frontmatter_text.strip().split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            # Parse lists like tags: [AI, Hermes Agent]
            if value.startswith("[") and value.endswith("]"):
                value = [v.strip().strip('"').strip("'") for v in value[1:-1].split(",")]
            metadata[key] = value

    return metadata, body


def load_single_document(filepath: str) -> Dict[str, Any]:
    """Load a single .md or .txt file and return {metadata, content}.

    Args:
        filepath: Absolute path to .md or .txt file.

    Returns:
        dict with keys: metadata, content
    """
    fpath = Path(filepath)
    suffix = fpath.suffix.lower()

    if suffix == ".md":
        content = fpath.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(content)
        lang = detect_doc_language(body, metadata.get("lang"))
        return {
            "metadata": {
                "source": fpath.name,
                "title": metadata.get("title", fpath.stem),
                "slug": metadata.get("slug", fpath.stem),
                "tags": metadata.get("tags", []),
                "category": metadata.get("category", ""),
                "filepath": str(fpath),
                "language": lang,
                "uploaded": True,
            },
            "content": body,
        }
    elif suffix == ".txt":
        content = fpath.read_text(encoding="utf-8")
        return {
            "metadata": {
                "source": fpath.name,
                "title": fpath.stem,
                "slug": fpath.stem,
                "tags": [],
                "category": "upload",
                "filepath": str(fpath),
                "uploaded": True,
            },
            "content": content,
        }
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def load_markdown_files(articles_dir: str) -> List[Dict[str, Any]]:
    """Load all Markdown files from directory. Return list of {metadata, content, filepath}."""
    docs = []
    path = Path(articles_dir)
    if not path.exists():
        print(f"[RAG] Articles dir not found: {articles_dir}")
        return docs

    for fpath in sorted(path.rglob("*.md")):
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

    print(f"[RAG] Loaded {len(docs)} documents from {articles_dir}")
    return docs
