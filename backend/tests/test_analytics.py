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
    mock_redis.zrangebyscore = AsyncMock(return_value=["100", "200", "150", "300", "250"])
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
    mock_redis.zrangebyscore = AsyncMock(return_value=[])
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
    assert data["hitRate"] == 0
    assert data["saves"] == 0


@pytest.mark.asyncio
async def test_cache_with_hits(mock_redis):
    mock_redis.get = AsyncMock(side_effect=lambda k: {
        "aureon:stats:cache_hits": "80",
        "aureon:stats:cache_misses": "20",
    }.get(k))
    app.dependency_overrides[get_redis_or_none] = lambda: mock_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/rag/analytics/cache")
    assert resp.status_code == 200
    data = resp.json()
    assert data["hitRate"] == 80.0
    assert data["saves"] == 80
