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
    """When Redis is None, get_stats returns 503 with structured error JSON."""
    app.dependency_overrides[get_redis_or_none] = lambda: None

    with patch("app.cache.redis_client._get_redis", return_value=None):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/rag/stats")

    assert resp.status_code == 503
    data = resp.json()
    assert data["error"] == "RedisUnavailableError"
    assert "Redis" in data["detail"]


@pytest.mark.asyncio
async def test_vector_store_error():
    """When vector store fails, get_stats returns 500 with structured error JSON."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.zrangebyscore = AsyncMock(return_value=[])

    app.dependency_overrides[get_redis_or_none] = lambda: mock_redis

    with patch("app.cache.redis_client._get_redis", return_value=mock_redis), \
         patch("app.api.rag_stats.get_collection_stats", side_effect=Exception("Chroma corrupted")):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/rag/stats")

    assert resp.status_code == 500
    data = resp.json()
    assert data["error"] == "VectorStoreError"
    assert "Chroma corrupted" in data["detail"]


@pytest.mark.asyncio
async def test_redis_operation_error():
    """When Redis raises an exception mid-operation, returns 503."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=Exception("Connection reset"))

    app.dependency_overrides[get_redis_or_none] = lambda: mock_redis

    with patch("app.cache.redis_client._get_redis", return_value=mock_redis):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/rag/stats")

    assert resp.status_code == 503
    data = resp.json()
    assert data["error"] == "RedisUnavailableError"
    assert "Connection reset" in data["detail"]
