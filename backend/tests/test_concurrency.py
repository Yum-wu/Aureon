"""Tests for concurrency rate limiting module."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException


@pytest.fixture
def concurrency_module():
    """Import concurrency module with fresh state."""
    import importlib
    import app.concurrency
    importlib.reload(app.concurrency)
    return app.concurrency


class TestSemaphoreLimits:
    """Test that semaphores enforce concurrency limits."""

    @pytest.mark.asyncio
    async def test_llm_semaphore_allows_concurrent_calls(self, concurrency_module):
        """LLM semaphore should allow calls within limit."""
        cm = concurrency_module
        results = []

        async def mock_call():
            async with cm.llm_call_with_semaphore("deepseek-chat"):
                results.append(True)
                await asyncio.sleep(0.01)

        await asyncio.gather(*[mock_call() for _ in range(5)])
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_rag_semaphore_allows_concurrent_calls(self, concurrency_module):
        """RAG pipeline semaphore should allow calls within limit."""
        cm = concurrency_module
        results = []

        async def mock_call():
            async with cm.rag_pipeline_semaphore():
                results.append(True)
                await asyncio.sleep(0.01)

        await asyncio.gather(*[mock_call() for _ in range(5)])
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_queue_timeout_returns_503(self, concurrency_module):
        """Should raise HTTPException 503 when queue times out."""
        cm = concurrency_module
        original_timeout = cm.QUEUE_TIMEOUT_SECONDS
        cm.QUEUE_TIMEOUT_SECONDS = 0.01

        sem = cm._LLM_SEMAPHORES.get("test-model")
        if sem is None:
            cm._LLM_SEMAPHORES["test-model"] = asyncio.Semaphore(1)
            sem = cm._LLM_SEMAPHORES["test-model"]

        await sem.acquire()

        with pytest.raises(HTTPException) as exc_info:
            async with cm.llm_call_with_semaphore("test-model"):
                pass

        assert exc_info.value.status_code == 503
        sem.release()
        cm.QUEUE_TIMEOUT_SECONDS = original_timeout


class TestConnectionStats:
    """Test connection statistics reporting."""

    def test_get_stats_returns_dict(self, concurrency_module):
        """get_concurrency_stats should return a dict with expected keys."""
        stats = concurrency_module.get_concurrency_stats()
        assert isinstance(stats, dict)
        assert "llm_semaphores" in stats
        assert "rag_semaphore_available" in stats
        assert "queue_timeout_seconds" in stats
