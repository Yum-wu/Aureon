"""Qdrant vector store backend for RAG system.

Replaces ChromaDB for production deployments. Supports:
- Persistent storage with mmap for large collections
- GPU-accelerated index building
- Metadata filtering (language, source, etc.)
- Batch operations for indexing
"""
from typing import List, Dict, Any, Optional
import numpy as np

import structlog

logger = structlog.get_logger(__name__)

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        VectorParams, Distance, PointStruct, Filter,
        FieldCondition, MatchValue
    )
    HAS_QDRANT = True
except ImportError:
    HAS_QDRANT = False
    logger.warning("qdrant-client not installed, Qdrant backend unavailable")


class QdrantStore:
    """Qdrant vector store for RAG embeddings.

    Args:
        url: Qdrant server URL (default: http://localhost:6333)
        api_key: Optional API key for authentication
        collection_name: Name of the collection (default: aureon)
    """

    def __init__(
        self,
        url: str = "http://localhost:6333",
        api_key: str = "",
        collection_name: str = "aureon",
    ):
        if not HAS_QDRANT:
            raise ImportError("qdrant-client not installed. Run: pip install qdrant-client")

        self.url = url
        self.collection_name = collection_name
        self._client: Optional[QdrantClient] = None
        self._api_key = api_key

    def _get_client(self) -> QdrantClient:
        """Lazy-init Qdrant client."""
        if self._client is None:
            kwargs = {"url": self.url}
            if self._api_key:
                kwargs["api_key"] = self._api_key
            self._client = QdrantClient(**kwargs)
            logger.info("Qdrant client connected: %s", self.url)
        return self._client

    def create_collection(self, dimension: int = 1024, force: bool = False) -> None:
        """Create or recreate collection.

        Args:
            dimension: Vector dimension (default 1024 for BGE-large-zh)
            force: If True, delete existing collection first
        """
        client = self._get_client()

        if force:
            try:
                client.delete_collection(self.collection_name)
                logger.info("Deleted existing collection: %s", self.collection_name)
            except Exception:
                pass

        try:
            client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=dimension,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Created collection: %s (dim=%d)", self.collection_name, dimension)
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info("Collection already exists: %s", self.collection_name)
            else:
                raise

    def save_chunks(
        self,
        chunks: List[Dict[str, Any]],
        embeddings: np.ndarray,
        batch_size: int = 100,
    ) -> None:
        """Save chunks with pre-computed embeddings.

        Args:
            chunks: List of chunk dicts with 'text' and 'metadata'
            embeddings: Pre-computed embeddings array (N x dim)
            batch_size: Batch size for upsert operations
        """
        client = self._get_client()

        for start in range(0, len(chunks), batch_size):
            end = min(start + batch_size, len(chunks))
            points = []

            for i in range(start, end):
                chunk = chunks[i]
                meta = chunk.get("metadata", {})
                points.append(PointStruct(
                    id=i,
                    vector=embeddings[i].tolist(),
                    payload={
                        "text": chunk["text"],
                        "source": meta.get("source", ""),
                        "title": meta.get("title", ""),
                        "slug": meta.get("slug", ""),
                        "language": meta.get("language", "unknown"),
                        "parent_text": meta.get("parent_text", ""),
                        "parent_idx": meta.get("parent_idx", -1),
                    },
                ))

            client.upsert(collection_name=self.collection_name, points=points)

        logger.info("Saved %d chunks to Qdrant (%s)", len(chunks), self.collection_name)

    def retrieve(
        self,
        query_embedding: np.ndarray,
        top_k: int = 3,
        lang_filter: Optional[str] = None,
        score_threshold: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Retrieve top-k similar chunks.

        Args:
            query_embedding: Query vector (1D array)
            top_k: Number of results to return
            lang_filter: Optional language filter ("zh" or "en")
            score_threshold: Minimum similarity score

        Returns:
            List of chunk dicts with text, metadata, and score
        """
        client = self._get_client()

        query_filter = None
        if lang_filter:
            query_filter = Filter(
                must=[FieldCondition(key="language", match=MatchValue(value=lang_filter))]
            )

        results = client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding.tolist(),
            limit=top_k,
            query_filter=query_filter,
            score_threshold=score_threshold,
        )

        return [
            {
                "text": r.payload.get("text", ""),
                "metadata": {
                    "source": r.payload.get("source", ""),
                    "title": r.payload.get("title", ""),
                    "slug": r.payload.get("slug", ""),
                    "language": r.payload.get("language", "unknown"),
                    "parent_text": r.payload.get("parent_text", ""),
                    "parent_idx": r.payload.get("parent_idx", -1),
                    "cosine_score": r.score,
                },
                "score": r.score,
            }
            for r in results
        ]

    def delete_by_source(self, source_filename: str) -> int:
        """Delete all chunks from a specific source file.

        Args:
            source_filename: The source filename to delete

        Returns:
            Number of points deleted (approximate)
        """
        client = self._get_client()

        count_before = self.get_point_count()
        client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="source", match=MatchValue(value=source_filename))]
            ),
        )
        count_after = self.get_point_count()

        deleted = count_before - count_after
        logger.info("Deleted %d chunks for '%s' from Qdrant", deleted, source_filename)
        return deleted

    def get_point_count(self) -> int:
        """Get total number of points in collection."""
        client = self._get_client()
        info = client.get_collection(self.collection_name)
        return info.points_count

    def get_indexed_sources(self) -> set:
        """Get set of source filenames currently indexed."""
        client = self._get_client()
        # Scroll through all points to collect unique sources
        sources = set()
        offset = None
        while True:
            result = client.scroll(
                collection_name=self.collection_name,
                limit=100,
                offset=offset,
                with_payload=["source"],
            )
            points, next_offset = result
            for point in points:
                source = point.payload.get("source", "")
                if source:
                    sources.add(source)
            if next_offset is None:
                break
            offset = next_offset
        return sources

    def health_check(self) -> dict:
        """Check Qdrant connection and collection status."""
        try:
            client = self._get_client()
            collections = client.get_collections().collections
            collection_names = [c.name for c in collections]

            if self.collection_name in collection_names:
                info = client.get_collection(self.collection_name)
                return {
                    "status": "ok",
                    "collection": self.collection_name,
                    "points_count": info.points_count,
                    "qdrant_status": str(info.status),
                }
            else:
                return {
                    "status": "warning",
                    "message": f"Collection '{self.collection_name}' not found",
                    "available_collections": collection_names,
                }
        except Exception as e:
            return {"status": "error", "message": str(e)}