"""Redis connection management - async + sync clients with reconnection.

Extracted from redis_client.py for single-responsibility.
"""
import random
import time

import structlog

logger = structlog.get_logger()

# -- Async Redis client singleton --
_redis = None

# -- Sync Redis connection pool with exponential backoff --
_sync_redis_pool = None
_sync_redis_backoff = 0.0      # current backoff duration (seconds)
_sync_redis_last_attempt = 0.0  # timestamp of last failed attempt
_SYNC_BACKOFF_INITIAL = 0.1
_SYNC_BACKOFF_MAX = 30.0
_SYNC_BACKOFF_RESET_WINDOW = 60.0  # reset backoff after 60s of no attempts


def get_async_redis():
    """Return async Redis client singleton, or None if unavailable.

    Retries on every call when previously unavailable (Redis may start
    after app, e.g. Railway deploy).
    """
    global _redis
    if _redis is not None:
        return _redis
    from app.config import settings
    if not settings.redis_url:
        return None
    try:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        logger.info("Async Redis connected")
    except Exception as e:
        logger.warning("Async Redis unavailable (non-fatal): %s", e)
        _redis = None
    return _redis


def get_sync_redis():
    """Return sync Redis client singleton for background threads.

    Uses ConnectionPool for TCP connection reuse.
    Thread-safe: redis-py's Redis + ConnectionPool is thread-safe.

    Reconnection uses exponential backoff: 0.1s -> 0.2s -> 0.4s -> ... -> 30s max,
    with 10% jitter. Backoff resets after 60s of inactivity.
    """
    global _sync_redis_pool, _sync_redis_backoff, _sync_redis_last_attempt
    if _sync_redis_pool is not None:
        return _sync_redis_pool

    # Exponential backoff: skip reconnect attempt if within backoff window
    now = time.monotonic()
    if _sync_redis_backoff > 0:
        # Reset backoff if enough time has passed since last attempt
        if now - _sync_redis_last_attempt >= _SYNC_BACKOFF_RESET_WINDOW:
            _sync_redis_backoff = 0.0
        elif now - _sync_redis_last_attempt < _sync_redis_backoff:
            return None

    from app.config import settings
    if not settings.redis_url:
        _sync_redis_last_attempt = now
        _sync_redis_backoff = max(_SYNC_BACKOFF_INITIAL, _sync_redis_backoff * 2)
        return None
    try:
        import redis as redis_sync
        pool = redis_sync.ConnectionPool.from_url(
            settings.redis_url,
            decode_responses=False,
            socket_connect_timeout=2,
            socket_timeout=2,
            max_connections=10,
        )
        _sync_redis_pool = redis_sync.Redis(connection_pool=pool)
        _sync_redis_backoff = 0.0
        logger.info("Sync Redis connected (connection pool, max_connections=10)")
    except Exception as e:
        _sync_redis_last_attempt = now
        # Exponential backoff: 0.1s -> 0.2s -> 0.4s -> ... -> 30s max
        if _sync_redis_backoff <= 0:
            _sync_redis_backoff = _SYNC_BACKOFF_INITIAL
        else:
            _sync_redis_backoff = min(_sync_redis_backoff * 2, _SYNC_BACKOFF_MAX)
        # Add 10% jitter to prevent thundering herd
        jitter = _sync_redis_backoff * random.uniform(0.0, 0.1)
        _sync_redis_backoff += jitter
        # Log on first few failures and every 100th
        _fail_estimate = int(_sync_redis_backoff / _SYNC_BACKOFF_INITIAL)
        if _fail_estimate <= 3 or _fail_estimate % 100 == 0:
            logger.warning(
                "Sync Redis unavailable (backoff %.1fs, next retry in %.1fs): %s",
                _sync_redis_backoff, _sync_redis_backoff, e,
            )
    return _sync_redis_pool


def close_sync_redis():
    """Close sync Redis pool, called during app shutdown."""
    global _sync_redis_pool
    if _sync_redis_pool is not None:
        try:
            _sync_redis_pool.connection_pool.disconnect()
        except Exception as e:
            logger.debug("redis_pool_disconnect_failed", error=str(e))
        _sync_redis_pool = None


async def close_async_redis():
    """Reset async Redis client, called during app shutdown."""
    global _redis
    if _redis is not None and hasattr(_redis, "close"):
        try:
            await _redis.close()
        except Exception as e:
            logger.debug("async_redis_close_failed", error=str(e))
    _redis = None
