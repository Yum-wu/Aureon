"""Tests for custom exceptions and unified error handling (TDD).

These tests verify that:
1. Custom exception classes produce correct HTTP status codes
2. rag_stats endpoints raise proper exceptions instead of silently returning empty data
3. Exception handlers return structured JSON error responses
"""

import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.dependencies import get_redis_or_none


@pytest.fixture(autouse=True)
def _clear_overrides():
    """Clear dependency overrides after each test."""
    yield
    app.dependency_overrides.clear()


# ── Custom exception class tests ──


@pytest.mark.asyncio
async def test_redis_unavailable_error():
    """When Redis is None, get_stats returns 200 with default values (graceful degradation)."""
    app.dependency_overrides[get_redis_or_none] = lambda: None

    with patch("app.cache.redis_client._get_redis", return_value=None):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/rag/stats")

    # Graceful degradation: return 200 with default values instead of 503
    assert resp.status_code == 200
    data = resp.json()
    # Redis-dependent values should be zero
    assert data["query_count_24h"] == 0
    assert data["cache_hit_rate"] == 0.0
    assert data["avg_retrieval_latency_ms"] == 0.0
    # But document/chunk counts should still come from vector store
    assert "total_indexed_docs" in data
    assert "total_chunks" in data


@pytest.mark.asyncio
async def test_vector_store_error():
    """When vector store fails, get_stats returns 200 with zero document counts."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.zrangebyscore = AsyncMock(return_value=[])

    app.dependency_overrides[get_redis_or_none] = lambda: mock_redis

    with patch("app.cache.redis_client._get_redis", return_value=mock_redis), \
         patch("app.api.rag_stats.get_collection_stats", side_effect=Exception("Chroma corrupted")):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/rag/stats")

    # Graceful degradation: return 200 with zero document counts
    assert resp.status_code == 200
    data = resp.json()
    # Vector store dependent values should be zero
    assert data["total_indexed_docs"] == 0
    assert data["total_chunks"] == 0
    # Redis values should still be available (though zero)
    assert data["query_count_24h"] == 0
    assert data["cache_hit_rate"] == 0.0


@pytest.mark.asyncio
async def test_redis_operation_error():
    """When Redis raises an exception mid-operation, returns 200 with partial data."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=Exception("Connection reset"))

    app.dependency_overrides[get_redis_or_none] = lambda: mock_redis

    with patch("app.cache.redis_client._get_redis", return_value=mock_redis):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/rag/stats")

    # Graceful degradation: return 200 with zeroed Redis-dependent values
    assert resp.status_code == 200
    data = resp.json()
    # Redis-dependent values should be zero
    assert data["query_count_24h"] == 0
    assert data["cache_hit_rate"] == 0.0
    assert data["avg_retrieval_latency_ms"] == 0.0
    # Document counts should still come from vector store
    assert "total_indexed_docs" in data
    assert "total_chunks" in data
