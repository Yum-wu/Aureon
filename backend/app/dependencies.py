"""FastAPI dependency injection for Redis.

Provides reusable Redis dependencies for route handlers,
eliminating duplicate imports across router modules.
"""

from typing import Optional

from fastapi import HTTPException

from app.cache.redis_client import _get_redis


def get_redis():
    """Return Redis client or raise 503 if unavailable.

    Use this dependency when the endpoint requires Redis to function.
    """
    client = _get_redis()
    if not client:
        raise HTTPException(
            status_code=503,
            detail="Redis is not available",
        )
    return client


def get_redis_or_none() -> Optional[object]:
    """Return Redis client or None if unavailable.

    Use this dependency when the endpoint can degrade gracefully
    without Redis (e.g. analytics endpoints returning zeroed data).
    """
    client = _get_redis()
    return client if client else None
