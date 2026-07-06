"""Chunk quality gates."""

from __future__ import annotations

import re


DEFAULT_MIN_CHUNK_LEN = 100
DEFAULT_MIN_UNIQUE_RATIO = 0.3  # at least 30% distinct chars


def is_valid_chunk(text: str, *, min_len: int = DEFAULT_MIN_CHUNK_LEN) -> bool:
    """Reject empty / very short chunks."""
    return bool(text and text.strip() and len(text.strip()) >= min_len)


def is_informative_chunk(
    text: str, *, min_unique_ratio: float = DEFAULT_MIN_UNIQUE_RATIO
) -> bool:
    """Reject near-duplicate / low-information chunks.

    A chunk that is mostly repeated characters (e.g. "aaa...aaa") or
    boilerplate (e.g. all punctuation) adds noise to the index.
    """
    stripped = text.strip()
    if not stripped:
        return False

    tokens = re.findall(r"[\w\u4e00-\u9fff]+", stripped.lower())
    if len(set(tokens)) >= 5:
        return True

    unique = len(set(stripped))
    return (unique / len(stripped)) >= min_unique_ratio


def deduplicate_chunks(
    chunks: list[dict], *, key: str = "text"
) -> list[dict]:
    """Remove exact-duplicate chunks while preserving order."""
    seen: set[str] = set()
    result: list[dict] = []
    for chunk in chunks:
        sig = chunk.get(key, "")
        if sig not in seen:
            seen.add(sig)
            result.append(chunk)
    return result
