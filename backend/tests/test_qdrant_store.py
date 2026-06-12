"""Tests for Qdrant vector store backend."""
import numpy as np
from unittest.mock import MagicMock


class TestQdrantStore:
    """Test Qdrant store operations."""

    def test_create_collection(self):
        """Test collection creation with correct params."""
        from app.rag.qdrant_store import QdrantStore
        store = QdrantStore(url="http://localhost:6333")
        # Mock client
        store._client = MagicMock()
        store.create_collection(dimension=1024)
        store._client.create_collection.assert_called_once()

    def test_save_chunks(self):
        """Test batch saving of chunks."""
        from app.rag.qdrant_store import QdrantStore
        store = QdrantStore(url="http://localhost:6333")
        store._client = MagicMock()

        chunks = [
            {"text": "test chunk", "metadata": {"slug": "test", "title": "Test"}},
            {"text": "another chunk", "metadata": {"slug": "test2", "title": "Test2"}},
        ]
        embeddings = np.random.rand(2, 1024).astype(np.float32)

        store.save_chunks(chunks, embeddings)
        store._client.upsert.assert_called()

    def test_retrieve_top_k(self):
        """Test retrieval returns correct number of results."""
        from app.rag.qdrant_store import QdrantStore
        store = QdrantStore(url="http://localhost:6333")
        store._client = MagicMock()

        # Mock search results
        mock_result = MagicMock()
        mock_result.id = "chunk_0"
        mock_result.score = 0.95
        mock_result.payload = {"text": "test", "metadata": {"slug": "test"}}
        store._client.search.return_value = [mock_result]

        results = store.retrieve(query_embedding=np.random.rand(1024), top_k=3)
        assert len(results) <= 3
        assert results[0]["score"] == 0.95

    def test_delete_by_source(self):
        """Test deletion by source filename."""
        from app.rag.qdrant_store import QdrantStore
        store = QdrantStore(url="http://localhost:6333")
        store._client = MagicMock()

        store.delete_by_source("test.md")
        store._client.delete.assert_called()

    def test_get_collection_stats(self):
        """Test collection statistics."""
        from app.rag.qdrant_store import QdrantStore
        store = QdrantStore(url="http://localhost:6333")
        store._client = MagicMock()
        store._client.get_collection.return_value.points_count = 100

        count = store.get_point_count()
        assert count == 100
