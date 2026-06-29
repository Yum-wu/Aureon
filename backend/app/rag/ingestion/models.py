"""Ingestion data models."""

from dataclasses import dataclass
from typing import Any


@dataclass
class IngestedDocument:
    metadata: dict[str, Any]
    content: str


@dataclass
class ChunkRecord:
    text: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "metadata": self.metadata}
