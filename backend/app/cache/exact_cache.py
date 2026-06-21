# -*- coding: utf-8 -*-
"""Exact-match cache - token-bag dedup, memory fallback, Redis TTL.

Extracted from redis_client.py for single-responsibility.
"""
import hashlib
import random
import re
import time
from typing import Optional
import structlog

from app.cache.connection import get_async_redis
from app.cache.metrics import record_hit, record_miss, record_set, record_error

logger = structlog.get_logger()

# -- In-memory fallback cache --
_mem_cache: dict = {}
_MEM_TTL = 3600
_MEM_MAX_VALUE_BYTES = 512 * 1024
_CACHE_VERSION = "v16"


def _mem_cache_key(query: str, tenant_id: str = "default") -> str:
    raw = query.strip().lower()
    tokens = sorted(set(re.findall(r'[\w\u4e00-\u9fff]+', raw)))
    return f"llm_cache:{_CACHE_VERSION}:{tenant_id}:{hashlib.md5(' '.join(tokens).encode()).hexdigest()}"


def mem_get(query: str, tenant_id: str = "default") -> Optional[str]:
    """In-memory cache lookup with expiry check."""
    full_key = _mem_cache_key(query, tenant_id)
    entry = _mem_cache.get(full_key)
    if entry is None:
        return None
    value, expires_at = entry
    if time.monotonic() > expires_at:
        del _mem_cache[full_key]
        return None
    return value


def mem_set(query: str, response: str, ttl: int = _MEM_TTL, tenant_id: str = "default") -> None:
    """In-memory cache set with TTL jitter to prevent stampede."""
    if len(response) > _MEM_MAX_VALUE_BYTES:
        return
    jittered_ttl = ttl + (random.randint(0, 300) if ttl > 0 else 0)
    full_key = _mem_cache_key(query, tenant_id)
    _mem_cache[full_key] = (response, time.monotonic() + jittered_ttl)
    if len(_mem_cache) > 500:
        now = time.monotonic()
        expired = [k for k, (_, exp) in _mem_cache.items() if now > exp]
        for k in expired:
            del _mem_cache[k]
        if len(_mem_cache) > 500:
            oldest = sorted(_mem_cache.keys(), key=lambda k: _mem_cache[k][1])[:50]
            for k in oldest:
                del _mem_cache[k]


async def get_cached(query: str, tenant_id: str = "default") -> Optional[str]:
    """Async exact-match cache lookup: Redis then memory fallback."""
    start = time.monotonic()
    try:
        r = get_async_redis()
        if r:
            key = _mem_cache_key(query, tenant_id)
            val = await r.get(key)
            if val:
                record_hit("exact", (time.monotonic() - start) * 1000)
                return val
    except Exception as e:
        record_error()
        logger.debug("exact_cache_get_error", error=str(e))

    # Memory fallback
    val = mem_get(query, tenant_id)
    if val:
        record_hit("exact", (time.monotonic() - start) * 1000)
        return val

    record_miss((time.monotonic() - start) * 1000)
    return None


async def set_cached(query: str, response: str, ttl: int = 3600, tenant_id: str = "default") -> None:
    """Async exact-match cache set: Redis + memory."""
    mem_set(query, response, ttl, tenant_id)
    record_set()
    try:
        r = get_async_redis()
        if r:
            key = _mem_cache_key(query, tenant_id)
            jittered_ttl = ttl + random.randint(0, 300)
            await r.set(key, response, ex=jittered_ttl)
    except Exception as e:
        logger.debug("exact_cache_set_error", error=str(e))
