"""Text normalization helpers for ingestion."""

from __future__ import annotations


def normalize_text(text: str) -> str:
    """Normalize line endings and collapse noisy blank lines.

    Keeps intra-line spacing and indentation intact so code blocks,
    tables, and other layout-sensitive content do not get flattened.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized_lines: list[str] = []
    blank_run = 0

    for line in text.split("\n"):
        line = line.rstrip()
        if line.strip():
            blank_run = 0
            normalized_lines.append(line)
            continue

        blank_run += 1
        if blank_run == 1:
            normalized_lines.append("")

    return "\n".join(normalized_lines).strip("\n")
