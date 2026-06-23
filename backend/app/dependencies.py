# -*- coding: utf-8 -*-
"""FastAPI dependency injection for Redis, HTTP client, and Authentication.

Provides reusable dependencies for route handlers,
eliminating duplicate imports across router modules.
"""

from typing import Annotated, Any, Optional

import httpx
from fastapi import Depends, HTTPException, Request

from app.cache.redis_client import get_redis as _redis_getter


def get_http_client(request: Request) -> httpx.AsyncClient:
    """Dependency that returns the shared httpx.AsyncClient with connection pooling.

    Use this in route handlers or background tasks that need to make
    external HTTP calls. The client is created at startup and shared
    across all requests for TCP connection reuse.
    """
    return request.app.state.http_client


HttpClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]


def get_settings():
    """Dependency that returns the application Settings singleton."""
    from app.config import settings
    return settings


SettingsDep = Annotated[Any, Depends(get_settings)]


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
