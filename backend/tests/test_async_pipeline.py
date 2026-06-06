"""Tests for async RAG pipeline."""
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock


class TestAsyncPipeline:
    """Test async RAG pipeline functions."""

    @pytest.mark.asyncio
    async def test_hybrid_retrieve_async_returns_results(self):
        """Test async hybrid retrieve returns merged results."""
        from app.rag.qa_chain import hybrid_retrieve_async

        with patch("app.rag.qa_chain.retrieve_keyword", return_value=[
            {"text": "bm25 result", "metadata": {"slug": "test"}, "score": 0.9}
        ]), patch("app.rag.qa_chain.retrieve", return_value=[
            {"text": "vector result", "metadata": {"slug": "test2"}, "score": 0.8}
        ]):
            results = await hybrid_retrieve_async("test query", top_k=3)
            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_hybrid_retrieve_async_empty(self):
        """Test async hybrid retrieve with no results."""
        from app.rag.qa_chain import hybrid_retrieve_async

        with patch("app.rag.qa_chain.retrieve_keyword", return_value=[]), \
             patch("app.rag.qa_chain.retrieve", return_value=[]):
            results = await hybrid_retrieve_async("nonexistent", top_k=3)
            assert results == []

    @pytest.mark.asyncio
    async def test_rag_query_async_returns_response(self):
        """Test async RAG query returns proper response."""
        from app.rag.qa_chain import rag_query_async

        mock_llm = AsyncMock(return_value="Test answer")

        with patch("app.rag.qa_chain.hybrid_retrieve_async", return_value=[
            {"text": "context", "metadata": {"slug": "test", "title": "Test"}, "score": 0.9}
        ]), patch("app.rag.qa_chain.compress_context", return_value=[
            {"text": "context", "metadata": {"slug": "test", "title": "Test"}, "score": 0.9}
        ]):
            result = await rag_query_async("test query", mock_llm, top_k=3)
            assert result.answer is not None
