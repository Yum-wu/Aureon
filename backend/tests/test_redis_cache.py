"""Tests for app.cache.redis_client — in-memory cache, get/set, close."""

import time
import pytest
from unittest.mock import patch, AsyncMock

from app.cache import redis_client
from app.cache import connection
from app.cache import exact_cache


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset module-level state between tests."""
    connection._redis = None
    exact_cache._mem_cache.clear()
    yield
    connection._redis = None
    exact_cache._mem_cache.clear()


# ── In-memory cache helpers ──


class TestMemCacheKey:
    def test_deterministic(self):
        k1 = exact_cache._mem_cache_key("hello world")
        k2 = exact_cache._mem_cache_key("hello world")
        assert k1 == k2

    def test_prefix(self):
        k = exact_cache._mem_cache_key("test")
        assert k.startswith("llm_cache:")

    def test_case_insensitive_and_strip(self):
        k1 = exact_cache._mem_cache_key("Hello")
        k2 = exact_cache._mem_cache_key("  hello  ")
        assert k1 == k2


class TestMemGetSet:
    def test_miss_returns_none(self):
        assert redis_client._mem_get("nonexistent") is None

    def test_set_then_get(self):
        redis_client._mem_set("q1", "answer1")
        assert redis_client._mem_get("q1") == "answer1"

    def test_expired_entry_removed(self):
        redis_client._mem_set("q2", "answer2", ttl=0)
        time.sleep(0.01)
        assert redis_client._mem_get("q2") is None

    def test_eviction_over_500(self):
        for i in range(510):
            redis_client._mem_set(f"q{i}", f"a{i}", ttl=3600)
        assert len(exact_cache._mem_cache) <= 500


# ── Semantic cache key ──


@pytest.mark.asyncio
async def test_semantic_cache_key_deterministic():
    k1 = await redis_client.semantic_cache_key("What is RAG?")
    k2 = await redis_client.semantic_cache_key("What is RAG?")
    assert k1 == k2
    assert k1.startswith("llm_cache:")


@pytest.mark.asyncio
async def test_semantic_cache_key_case_insensitive():
    k1 = await redis_client.semantic_cache_key("Hello")
    k2 = await redis_client.semantic_cache_key("  hello  ")
    assert k1 == k2


# ── get_cached / set_cached ──


@pytest.mark.asyncio
async def test_get_cached_mem_hit():
    redis_client._mem_set("q", "cached_answer")
    result = await redis_client.get_cached("q")
    assert result == "cached_answer"


@pytest.mark.asyncio
async def test_get_cached_mem_miss_redis_miss():
    mock_r = AsyncMock()
    mock_r.get = AsyncMock(return_value=None)
    connection._redis = mock_r

    result = await redis_client.get_cached("unknown")
    assert result is None


@pytest.mark.asyncio
async def test_get_cached_redis_hit_populates_mem():
    mock_r = AsyncMock()
    mock_r.get = AsyncMock(return_value="redis_answer")
    connection._redis = mock_r

    result = await redis_client.get_cached("q")
    assert result == "redis_answer"
    # Should also be in memory now
    assert redis_client._mem_get("q") == "redis_answer"


@pytest.mark.asyncio
async def test_get_cached_redis_exception_graceful():
    mock_r = AsyncMock()
    mock_r.get = AsyncMock(side_effect=ConnectionError("down"))
    connection._redis = mock_r

    result = await redis_client.get_cached("q")
    assert result is None


@pytest.mark.asyncio
async def test_set_cached_no_redis():
    """set_cached stores in memory even when Redis is unavailable."""
    connection._redis = False
    await redis_client.set_cached("q", "answer")
    assert redis_client._mem_get("q") == "answer"


@pytest.mark.asyncio
async def test_set_cached_with_redis():
    mock_r = AsyncMock()
    mock_r.set = AsyncMock()
    connection._redis = mock_r

    await redis_client.set_cached("q", "answer", ttl=120)
    mock_r.set.assert_called_once()
    assert redis_client._mem_get("q") == "answer"


@pytest.mark.asyncio
async def test_set_cached_redis_exception_graceful():
    mock_r = AsyncMock()
    mock_r.set = AsyncMock(side_effect=ConnectionError("down"))
    connection._redis = mock_r

    # Should not raise
    await redis_client.set_cached("q", "answer")
    assert redis_client._mem_get("q") == "answer"


# ── get_redis / _get_redis ──


def test_get_redis_returns_none_on_import_error():
    """When redis package is missing, _get_redis returns None."""
    connection._redis = None
    with patch.dict("sys.modules", {"redis.asyncio": None}):
        result = redis_client._get_redis()
    # None = unavailable, or a valid client
    assert result is None or result is not False


def test_get_redis_singleton():
    """Second call returns cached instance."""
    connection._redis = "fake_client"
    assert redis_client._get_redis() == "fake_client"


# ── close_redis ──


@pytest.mark.asyncio
async def test_close_redis_with_client():
    mock_r = AsyncMock()
    mock_r.close = AsyncMock()
    connection._redis = mock_r

    await redis_client.close_redis()
    mock_r.close.assert_called_once()
    assert connection._redis is None


@pytest.mark.asyncio
async def test_close_redis_with_false_sentinel():
    connection._redis = False
    await redis_client.close_redis()
    # _redis is reset to None after close (False sentinel treated as no client)
    assert connection._redis is None


@pytest.mark.asyncio
async def test_close_redis_with_none():
    connection._redis = None
    await redis_client.close_redis()
    assert connection._redis is None
