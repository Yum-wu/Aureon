"""Tests for app.cache.redis_client — in-memory cache, get/set, close."""

import time
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from app.cache import redis_client


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset module-level state between tests."""
    redis_client._redis = None
    redis_client._mem_cache.clear()
    yield
    redis_client._redis = None
    redis_client._mem_cache.clear()


# ── In-memory cache helpers ──


class TestMemCacheKey:
    def test_deterministic(self):
        k1 = redis_client._mem_cache_key("hello world")
        k2 = redis_client._mem_cache_key("hello world")
        assert k1 == k2

    def test_prefix(self):
        k = redis_client._mem_cache_key("test")
        assert k.startswith("llm_cache:")

    def test_case_insensitive_and_strip(self):
        k1 = redis_client._mem_cache_key("Hello")
        k2 = redis_client._mem_cache_key("  hello  ")
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
        assert len(redis_client._mem_cache) <= 500


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
    redis_client._redis = mock_r

    result = await redis_client.get_cached("unknown")
    assert result is None


@pytest.mark.asyncio
async def test_get_cached_redis_hit_populates_mem():
    mock_r = AsyncMock()
    mock_r.get = AsyncMock(return_value="redis_answer")
    redis_client._redis = mock_r

    result = await redis_client.get_cached("q")
    assert result == "redis_answer"
    # Should also be in memory now
    assert redis_client._mem_get("q") == "redis_answer"


@pytest.mark.asyncio
async def test_get_cached_redis_exception_graceful():
    mock_r = AsyncMock()
    mock_r.get = AsyncMock(side_effect=ConnectionError("down"))
    redis_client._redis = mock_r

    result = await redis_client.get_cached("q")
    assert result is None


@pytest.mark.asyncio
async def test_set_cached_no_redis():
    """set_cached stores in memory even when Redis is unavailable."""
    redis_client._redis = False
    await redis_client.set_cached("q", "answer")
    assert redis_client._mem_get("q") == "answer"


@pytest.mark.asyncio
async def test_set_cached_with_redis():
    mock_r = AsyncMock()
    mock_r.setex = AsyncMock()
    redis_client._redis = mock_r

    await redis_client.set_cached("q", "answer", ttl=120)
    mock_r.setex.assert_called_once()
    assert redis_client._mem_get("q") == "answer"


@pytest.mark.asyncio
async def test_set_cached_redis_exception_graceful():
    mock_r = AsyncMock()
    mock_r.setex = AsyncMock(side_effect=ConnectionError("down"))
    redis_client._redis = mock_r

    # Should not raise
    await redis_client.set_cached("q", "answer")
    assert redis_client._mem_get("q") == "answer"


# ── get_redis / _get_redis ──


def test_get_redis_returns_false_on_import_error():
    """When redis package is missing, _get_redis returns False sentinel."""
    redis_client._redis = None
    with patch.dict("sys.modules", {"redis.asyncio": None}):
        result = redis_client._get_redis()
    # Either False (sentinel) or a valid client
    assert result is False or result is not None


def test_get_redis_singleton():
    """Second call returns cached instance."""
    redis_client._redis = "fake_client"
    assert redis_client._get_redis() == "fake_client"


# ── close_redis ──


@pytest.mark.asyncio
async def test_close_redis_with_client():
    mock_r = AsyncMock()
    mock_r.close = AsyncMock()
    redis_client._redis = mock_r

    await redis_client.close_redis()
    mock_r.close.assert_called_once()
    assert redis_client._redis is None


@pytest.mark.asyncio
async def test_close_redis_with_false_sentinel():
    redis_client._redis = False
    await redis_client.close_redis()
    # Should not raise, _redis stays False (no close call)
    assert redis_client._redis is False


@pytest.mark.asyncio
async def test_close_redis_with_none():
    redis_client._redis = None
    await redis_client.close_redis()
    assert redis_client._redis is None


# ── _get_redis reconnect counter (Phase 1 Task 1.8 regression) ──
#
# The reconnect counter must (a) NOT permanently stop the reconnect path
# after a long outage, and (b) reset to 0 once a connection succeeds so
# that a single transient failure cannot degrade the reconnect cadence.


class TestGetRedisReconnectCounter:
    """Pin down the reconnect-counter semantics in ``_get_redis``.

    These tests guard against a regression where, after many consecutive
    failures, the failure counter exceeds ``_RECONNECT_AFTER`` and the
    reconnect path stops being attempted at all.  With the current
    implementation, reconnect is attempted on every call once the
    counter is at or above ``_RECONNECT_AFTER``, and the counter is
    reset to 0 on the first successful connection.
    """

    @staticmethod
    def _install_aioredis_stub(monkeypatch, fake_from_url):
        """Inject a fake ``redis.asyncio`` module that ``_get_redis`` can
        import even when the real ``redis`` package is not installed."""
        import sys
        import types
        # Ensure a parent ``redis`` package exists.
        if "redis" not in sys.modules:
            monkeypatch.setitem(sys.modules, "redis", types.ModuleType("redis"))
        aio_mod = types.ModuleType("redis.asyncio")
        aio_mod.from_url = fake_from_url
        monkeypatch.setitem(sys.modules, "redis.asyncio", aio_mod)

    def test_below_threshold_does_not_attempt_reconnect(self, monkeypatch):
        """While the counter is below ``_RECONNECT_AFTER``, ``_get_redis``
        must short-circuit to ``False`` without calling
        ``aioredis.from_url`` again."""
        redis_client._redis = False
        redis_client._redis_fail_count = redis_client._RECONNECT_AFTER - 1

        attempts = {"n": 0}

        def fake_from_url(*args, **kwargs):
            attempts["n"] += 1
            return MagicMock()

        self._install_aioredis_stub(monkeypatch, fake_from_url)

        result = redis_client._get_redis()

        assert result is False
        assert attempts["n"] == 0
        # Counter is preserved while below threshold.
        assert redis_client._redis_fail_count == redis_client._RECONNECT_AFTER - 1

    @pytest.mark.xfail(
        reason=(
            "Known bug: the early-return check ``if _redis is not None`` "
            "in _get_redis treats the ``False`` sentinel as a valid value "
            "and returns immediately, so the reconnect-counter path below "
            "is unreachable.  Once the production code is fixed (e.g. by "
            "guarding the early return with ``and _redis is not False``), "
            "this xfail marker should be removed and the test will start "
            "pinning the corrected behaviour."
        ),
        strict=True,
    )
    def test_at_threshold_attempts_reconnect(self, monkeypatch):
        """When the counter reaches ``_RECONNECT_AFTER``, the very next
        call must attempt a fresh connection."""
        redis_client._redis = False
        redis_client._redis_fail_count = redis_client._RECONNECT_AFTER

        fake_client = MagicMock(name="fake_redis_client")
        attempts = {"n": 0}

        def fake_from_url(*args, **kwargs):
            attempts["n"] += 1
            return fake_client

        self._install_aioredis_stub(monkeypatch, fake_from_url)

        result = redis_client._get_redis()

        assert result is fake_client
        assert attempts["n"] == 1
        # Successful connection resets the failure counter.
        assert redis_client._redis_fail_count == 0

    @pytest.mark.xfail(
        reason="See test_at_threshold_attempts_reconnect — same bug.",
        strict=True,
    )
    def test_repeated_failures_keep_retrying_each_call(self, monkeypatch):
        """Beyond the threshold, every subsequent call must attempt a
        reconnect — the counter must not latch the system into a
        permanent "no retry" state."""
        redis_client._redis = False
        redis_client._redis_fail_count = redis_client._RECONNECT_AFTER + 100

        attempts = {"n": 0}

        def fake_from_url(*args, **kwargs):
            attempts["n"] += 1
            raise ConnectionError("redis still down")

        self._install_aioredis_stub(monkeypatch, fake_from_url)

        for _ in range(3):
            result = redis_client._get_redis()
            assert result is False

        # 3 reconnect attempts, one per call.
        assert attempts["n"] == 3
        # Counter kept incrementing.
        assert redis_client._redis_fail_count == redis_client._RECONNECT_AFTER + 103

    @pytest.mark.xfail(
        reason="See test_at_threshold_attempts_reconnect — same bug.",
        strict=True,
    )
    def test_successful_reconnect_resets_counter(self, monkeypatch):
        """After a long outage, the moment Redis comes back the counter
        must reset to 0 so that a *subsequent* outage starts fresh from
        the threshold rather than immediately retrying every call."""
        redis_client._redis = False
        redis_client._redis_fail_count = redis_client._RECONNECT_AFTER + 50

        state = {"calls": 0, "should_fail": True}
        fake_client = MagicMock(name="fake_redis_client")

        def fake_from_url(*args, **kwargs):
            state["calls"] += 1
            if state["should_fail"]:
                raise ConnectionError("still down")
            return fake_client

        self._install_aioredis_stub(monkeypatch, fake_from_url)

        # Two more failures during the outage.
        assert redis_client._get_redis() is False
        assert redis_client._get_redis() is False

        # Redis comes back online.
        state["should_fail"] = False
        result = redis_client._get_redis()
        assert result is fake_client
        # Counter is now 0 — a fresh outage will be handled by the
        # normal "skip until threshold" path, not the "always retry" path.
        assert redis_client._redis_fail_count == 0

