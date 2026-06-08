"""Abstract vector store interface for pluggable backends.

Allows switching between ChromaDB and pgvector without changing
RAG pipeline code. Only implement pgvector if client requires it.

Reference: docs/superpowers/specs/2026-06-08-krl-dutch-delivery-plan.md §4.2
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class VectorStoreInterface(ABC):
    """Abstract base for vector store implementations."""

    @abstractmethod
    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar chunks.

        Returns list of dicts with 'text', 'metadata', 'score' keys.
        """
        ...

    @abstractmethod
    def upsert(self, chunks: List[Dict[str, Any]]) -> None:
        """Insert or update chunks in the store."""
        ...

    @abstractmethod
    def delete(self, ids: List[str]) -> None:
        """Delete chunks by ID."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Return total number of chunks in the store."""
        ...
