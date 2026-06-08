"""Tests for /api/rag/analytics/* endpoints."""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.dependencies import get_redis_or_none


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def mock_redis():
    client = AsyncMock()
    with patch("app.cache.redis_client._get_redis", return_value=client):
        yield client


# ── /api/rag/analytics/usage ──


@pytest.mark.asyncio
async def test_usage_no_redis():
    app.dependency_overrides[get_redis_or_none] = lambda: None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/rag/analytics/usage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["timeRange"] == "24h"


@pytest.mark.asyncio
async def test_usage_with_redis(mock_redis):
    mock_redis.get = AsyncMock(return_value="42")
    mock_redis.hgetall = AsyncMock(return_value={"chat": "30", "rag": "12"})
    app.dependency_overrides[get_redis_or_none] = lambda: mock_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/rag/analytics/usage", params={"time_range": "7d"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 42
    assert data["byIntent"]["chat"] == 30
    assert data["byIntent"]["rag"] == 12


@pytest.mark.asyncio
async def test_usage_redis_error(mock_redis):
    mock_redis.get = AsyncMock(side_effect=ConnectionError("down"))
    app.dependency_overrides[get_redis_or_none] = lambda: mock_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/rag/analytics/usage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0


# ── /api/rag/analytics/latency ──


@pytest.mark.asyncio
async def test_latency_no_redis():
    app.dependency_overrides[get_redis_or_none] = lambda: None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/rag/analytics/latency")
    assert resp.status_code == 200
    data = resp.json()
    assert data["avg"] == 0
    assert "p95" in data
    assert "p99" in data


@pytest.mark.asyncio
async def test_latency_with_data(mock_redis):
    # Setup mock to return latency scores from sorted set (score = latency_ms)
    mock_redis.zrange = AsyncMock(return_value=[
        (b"ts1:abc", 100.0), (b"ts2:def", 200.0), (b"ts3:ghi", 150.0),
        (b"ts4:jkl", 300.0), (b"ts5:mno", 250.0),
    ])
    app.dependency_overrides[get_redis_or_none] = lambda: mock_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/rag/analytics/latency")
    assert resp.status_code == 200
    data = resp.json()
    assert data["avg"] > 0
    assert data["p95"] > 0


@pytest.mark.asyncio
async def test_latency_empty_data(mock_redis):
    mock_redis.zrange = AsyncMock(return_value=[])
    app.dependency_overrides[get_redis_or_none] = lambda: mock_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/rag/analytics/latency")
    assert resp.status_code == 200
    data = resp.json()
    assert data["avg"] == 0


# ── /api/rag/analytics/tokens ──


@pytest.mark.asyncio
async def test_tokens_no_redis():
    app.dependency_overrides[get_redis_or_none] = lambda: None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/rag/analytics/tokens")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["cost"] == 0


@pytest.mark.asyncio
async def test_tokens_with_data(mock_redis):
    mock_redis.hgetall = AsyncMock(return_value={"input": "100000", "output": "50000", "queries": "100"})
    app.dependency_overrides[get_redis_or_none] = lambda: mock_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/rag/analytics/tokens")
    assert resp.status_code == 200
    data = resp.json()
    assert data["input"] == 100000
    assert data["output"] == 50000
    assert data["total"] == 150000
    assert data["cost"] >= 0
    assert data["costPerQuery"] >= 0


# ── /api/rag/analytics/cache ──


@pytest.mark.asyncio
async def test_cache_no_redis():
    app.dependency_overrides[get_redis_or_none] = lambda: None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/rag/analytics/cache")
    assert resp.status_code == 200
    data = resp.json()
    # Support both old (hitRate) and new (hit_rate) formats
    assert data.get("hitRate", data.get("hit_rate", 0)) == 0
    assert data.get("saves", data.get("sets", 0)) == 0


@pytest.mark.asyncio
async def test_cache_with_hits():
    """Cache endpoint now reads from get_cache_metrics() (in-memory), not Redis."""
    fake_metrics = {
        "exact_hits": 60,
        "semantic_hits": 20,
        "misses": 20,
        "total_lookups": 100,
        "hit_rate": 0.8,
        "exact_hit_rate": 0.6,
        "semantic_hit_rate": 0.2,
        "sets": 80,
        "errors": 0,
        "avg_latency_ms": 5.0,
        "p50_latency_ms": 3.0,
        "p90_latency_ms": 8.0,
        "p99_latency_ms": 12.0,
        "error_rate": 0.0,
        "latency_sample_size": 100,
    }
    with patch("app.cache.redis_client.get_cache_metrics", return_value=fake_metrics):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/rag/analytics/cache")
    assert resp.status_code == 200
    data = resp.json()
    # New response format uses snake_case
    assert data["hit_rate"] == 0.8
    assert data["sets"] == 80
    assert data["exact_hits"] == 60
    assert data["semantic_hits"] == 20
