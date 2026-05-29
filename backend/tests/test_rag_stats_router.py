"""Tests for /api/rag/stats endpoint."""

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


@pytest.fixture
def mock_redis():
    """Provide a mock Redis client that also patches direct _get_redis calls."""
    client = AsyncMock()
    with patch("app.cache.redis_client._get_redis", return_value=client):
        yield client


@pytest.mark.asyncio
async def test_get_stats_returns_expected_fields(mock_redis):
    """Stats endpoint returns all required fields with correct types."""
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.zrangebyscore = AsyncMock(return_value=["100", "200"])

    app.dependency_overrides[get_redis_or_none] = lambda: mock_redis

    with patch("app.api.rag_stats.get_collection_stats", return_value=(5, 120)):
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
    """When Redis is unavailable, endpoint raises 503 error."""
    app.dependency_overrides[get_redis_or_none] = lambda: None

    with patch("app.cache.redis_client._get_redis", return_value=None):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/rag/stats")

    assert resp.status_code == 503
    data = resp.json()
    assert data["error"] == "RedisUnavailableError"


# ── /api/rag/queries/recent ──


@pytest.mark.asyncio
async def test_get_recent_queries_returns_list(mock_redis):
    """Recent queries endpoint returns a queries list when Redis has data."""
    mock_redis.lrange = AsyncMock(return_value=[
        "2026-05-29T10:00:00+00:00|什么是 RAG?|3|120.5",
        "2026-05-29T09:58:00+00:00|如何部署?|2|85.0",
    ])

    app.dependency_overrides[get_redis_or_none] = lambda: mock_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/rag/queries/recent")

    assert resp.status_code == 200
    data = resp.json()
    assert "queries" in data
    assert isinstance(data["queries"], list)
    assert len(data["queries"]) == 2


@pytest.mark.asyncio
async def test_get_recent_queries_with_limit(mock_redis):
    """Limit parameter controls the number of returned queries."""
    mock_redis.lrange = AsyncMock(return_value=[
        "2026-05-29T10:00:00+00:00|q1|1|50.0",
    ])

    app.dependency_overrides[get_redis_or_none] = lambda: mock_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/rag/queries/recent", params={"limit": 1})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["queries"]) <= 1

    # Verify lrange was called with limit-1 as stop index
    mock_redis.lrange.assert_called_once()
    call_args = mock_redis.lrange.call_args
    assert call_args[0][2] == 0  # start


@pytest.mark.asyncio
async def test_recent_query_structure(mock_redis):
    """Each query entry has the correct fields and types."""
    mock_redis.lrange = AsyncMock(return_value=[
        "2026-05-29T10:00:00+00:00|什么是 RAG?|3|120.5",
    ])

    app.dependency_overrides[get_redis_or_none] = lambda: mock_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/rag/queries/recent")

    assert resp.status_code == 200
    query = resp.json()["queries"][0]

    assert query["query"] == "什么是 RAG?"
    assert query["sources_count"] == 3
    assert isinstance(query["latency_ms"], float)
    assert query["latency_ms"] == 120.5
    assert query["timestamp"] == "2026-05-29T10:00:00+00:00"


@pytest.mark.asyncio
async def test_recent_queries_redis_unavailable():
    """When Redis is unavailable, returns 503 error instead of empty list."""
    app.dependency_overrides[get_redis_or_none] = lambda: None

    with patch("app.cache.redis_client._get_redis", return_value=None):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/rag/queries/recent")

    assert resp.status_code == 503
    data = resp.json()
    assert data["error"] == "RedisUnavailableError"
