"""Tests for async RAG pipeline.

These tests require external services (Qdrant, embedding API) and are
marked as integration tests. Run with: pytest -m integration
"""
import pytest
from unittest.mock import AsyncMock


@pytest.mark.integration
class TestAsyncPipeline:
    """Test async RAG pipeline functions (requires Qdrant + embedding API)."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_hybrid_retrieve_async_returns_results(self):
        """Test async hybrid retrieve returns merged results."""
        from app.rag.indexer import hybrid_retrieve_async
        results = await hybrid_retrieve_async("test query", top_k=3)
        assert isinstance(results, list)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_hybrid_retrieve_async_empty(self):
        """Test async hybrid retrieve with no results."""
        from app.rag.indexer import hybrid_retrieve_async
        results = await hybrid_retrieve_async("nonexistent", top_k=3)
        assert results == []

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_rag_query_async_returns_response(self):
        """Test async RAG query returns proper response."""
        from app.rag.indexer import rag_query_async

        mock_llm = AsyncMock(return_value="Test answer")
        result = await rag_query_async("test query", mock_llm, top_k=3)
        assert result.answer is not None
