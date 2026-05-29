"""Tests for /api/rag/stats endpoint."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_get_stats_returns_expected_fields():
    """Stats endpoint returns all required fields with correct types."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.zrangebyscore = AsyncMock(return_value=["100", "200"])

    with patch("app.api.rag_stats._get_redis", return_value=mock_redis), \
         patch("app.api.rag_stats.get_collection_stats", return_value=(5, 120)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/rag/stats")

    assert resp.status_code == 200
    data = resp.json()

    required_fields = [
        "cache_hit_rate",
        "query_count_24h",
        "avg_retrieval_latency_ms",
        "total_indexed_docs",
        "total_chunks",
    ]
    for field in required_fields:
        assert field in data, f"Missing field: {field}"

    # Verify types
    assert isinstance(data["cache_hit_rate"], float)
    assert isinstance(data["query_count_24h"], int)
    assert isinstance(data["avg_retrieval_latency_ms"], (int, float))
    assert isinstance(data["total_indexed_docs"], int)
    assert isinstance(data["total_chunks"], int)

    # Verify Chroma stats are passed through
    assert data["total_indexed_docs"] == 5
    assert data["total_chunks"] == 120

    # Verify latency average from mock data ["100", "200"]
    assert data["avg_retrieval_latency_ms"] == 150.0


@pytest.mark.asyncio
async def test_get_stats_with_redis_unavailable():
    """When Redis is unavailable, endpoint returns default values without crashing."""
    with patch("app.api.rag_stats._get_redis", return_value=None), \
         patch("app.api.rag_stats.get_collection_stats", return_value=(0, 0)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/rag/stats")

    assert resp.status_code == 200
    data = resp.json()

    assert data["cache_hit_rate"] == 0.0
    assert data["query_count_24h"] == 0
    assert data["avg_retrieval_latency_ms"] == 0.0
    assert data["total_indexed_docs"] == 0
    assert data["total_chunks"] == 0
