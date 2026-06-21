"""Redis connection management - async + sync clients with reconnection.

Extracted from redis_client.py for single-responsibility.
"""
import structlog

logger = structlog.get_logger()

# -- Async Redis client singleton --
_redis = None

# -- Sync Redis connection pool --
_sync_redis_pool = None
_sync_redis_fail_count = 0
_SYNC_RECONNECT_AFTER = 5


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
    """
    global _sync_redis_pool, _sync_redis_fail_count
    if _sync_redis_pool is not None:
        return _sync_redis_pool
    if _sync_redis_fail_count >= _SYNC_RECONNECT_AFTER:
        return None
    from app.config import settings
    if not settings.redis_url:
        _sync_redis_fail_count += 1
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
        _sync_redis_fail_count = 0
        logger.info("Sync Redis connected (connection pool, max_connections=10)")
    except Exception as e:
        _sync_redis_fail_count += 1
        if _sync_redis_fail_count <= 3 or _sync_redis_fail_count % 100 == 0:
            logger.warning("Sync Redis unavailable (fail #%d): %s", _sync_redis_fail_count, e)
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


def close_async_redis():
    """Reset async Redis client, called during app shutdown."""
    global _redis
    _redis = None
