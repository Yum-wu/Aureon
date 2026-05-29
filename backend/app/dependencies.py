"""FastAPI dependency injection for Redis.

Provides reusable Redis dependencies for route handlers,
eliminating duplicate imports across router modules.
"""

from typing import Any, Optional

from fastapi import HTTPException

from app.cache.redis_client import get_redis as _redis_getter


def require_redis() -> Any:
    """Dependency that raises 503 if Redis unavailable.

    Use this when the endpoint requires Redis to function.
    """
    client = _redis_getter()
    if client is None or client is False:
        raise HTTPException(
            status_code=503,
            detail="Redis is not available",
        )
    return client


def get_redis_or_none() -> Optional[Any]:
    """Dependency that returns None if Redis unavailable.

    Use this when the endpoint can degrade gracefully
    without Redis (e.g. analytics endpoints returning zeroed data).
    """
    client = _redis_getter()
    if client is None or client is False:
        return None
    return client
