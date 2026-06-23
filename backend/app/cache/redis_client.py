"""Cache public API - delegates to connection, exact_cache, metrics.

This module preserves backward compatibility: all existing imports from
redis_client continue to work. Functions not yet extracted to sub-modules
(semantic cache integration, LLM cache, utilities) remain here.
"""
import hashlib
import re
import threading
import time
from typing import Optional, Dict, Any
import structlog

from app.multi_tenant.middleware import get_current_tenant_id

# Re-exports from sub-modules (backward compatibility)
from app.cache.connection import (
    get_async_redis,
    get_sync_redis,
    close_sync_redis,
    close_async_redis,
)
from app.cache.exact_cache import (
    get_cached,
    set_cached,
    mem_get,
    mem_set,
    _mem_cache_key,
    _mem_cache,
)
from app.cache.metrics import (
    get_metrics,
    record_hit,
    record_miss,
    record_set,
    record_error,
)

logger = structlog.get_logger()

# Bump to invalidate all cached RAG responses (e.g. after retrieval logic changes)
_CACHE_VERSION = "v16"  # v16: semantic dedup via token bag


# Backward-compatible aliases

def get_redis():
    """Public interface for getting async Redis client (backward compat)."""
    return get_async_redis()


async def close_redis():
    """Close async Redis connection (backward compat alias for close_async_redis)."""
    await close_async_redis()


# Old private API names used by tests (backward compat)
_mem_get = mem_get
_mem_set = mem_set
_get_redis = get_async_redis
_get_sync_redis = get_sync_redis


# Semantic Cache Integration (not yet extracted)
# Two-layer cache: exact (hash) + semantic (vector similarity)
# Gracefully degrades when SemanticLLMCache is unavailable

_semantic_cache_instance = None
_semantic_cache_lock = threading.Lock()


def get_semantic_cache_instance():
    """Get or create SemanticLLMCache singleton.

    Lazy-loads the SemanticLLMCache module and creates a singleton instance.
    Returns None if the module is unavailable (graceful degradation).
    """
    global _semantic_cache_instance

    if _semantic_cache_instance is not None:  # Fast path (no lock)
        return _semantic_cache_instance

    with _semantic_cache_lock:
        if _semantic_cache_instance is not None:  # Double-check
            return _semantic_cache_instance

        try:
            from app.cache.semantic_cache import SemanticLLMCache
            _semantic_cache_instance = SemanticLLMCache(
                similarity_threshold=0.92,
                default_ttl=3600,  # Match Redis TTL
                max_cache_size=10000,
            )
            logger.info("Semantic cache singleton created")
            return _semantic_cache_instance
        except ImportError:
            logger.debug("semantic_cache module not available, using exact-match only")
            return None
        except Exception as e:
            logger.warning("Failed to create semantic cache: %s (non-fatal)", e)
            return None


def increment_cache_miss():
    """Increment miss counter when LLM is actually called."""
    record_miss(0.0)


def get_cache_metrics() -> Dict[str, Any]:
    """Return cache performance metrics (detailed, backward compat).

    Returns:
        Dictionary with hit/miss counts, rates, and latency percentiles
    """
    # Delegate to metrics module and enrich with percentiles
    base = get_metrics()

    # Add detailed percentiles if latency data available
    from app.cache.metrics import _cache_metrics
    latencies = list(_cache_metrics["latencies"])

    if latencies:
        latencies_sorted = sorted(latencies)
        p50_idx = int(len(latencies_sorted) * 0.5)
        p90_idx = int(len(latencies_sorted) * 0.9)
        p99_idx = int(len(latencies_sorted) * 0.99)
        base["p50_latency_ms"] = latencies_sorted[min(p50_idx, len(latencies_sorted) - 1)]
        base["p90_latency_ms"] = latencies_sorted[min(p90_idx, len(latencies_sorted) - 1)]
        base["p99_latency_ms"] = latencies_sorted[min(p99_idx, len(latencies_sorted) - 1)]
        base["latency_sample_size"] = len(latencies)
    else:
        base["p50_latency_ms"] = 0.0
        base["p90_latency_ms"] = 0.0
        base["p99_latency_ms"] = 0.0
        base["latency_sample_size"] = 0

    # Ensure all expected keys present
    base.setdefault("exact_hit_rate", 0.0)
    base.setdefault("semantic_hit_rate", 0.0)
    base.setdefault("error_rate", 0.0)

    return base


async def semantic_cache_key(query: str) -> str:
    """Return a deterministic cache key for a query.

    Uses normalized token bag (sorted unique tokens) for semantic dedup.
    Queries with same tokens (regardless of order/punctuation) share a key.
    Example: 'What is RAG?' and 'RAG is what' produce the same key.
    """
    raw = query.strip().lower()
    # Normalize: remove punctuation, collapse whitespace, sort tokens
    tokens = sorted(set(re.findall(r'[\w\u4e00-\u9fff]+', raw)))
    token_hash = hashlib.md5(" ".join(tokens).encode()).hexdigest()
    return f"llm_cache:{_CACHE_VERSION}:{token_hash}"


async def clear_cache_by_prefix(prefix: str) -> int:
    """Delete all keys matching prefix using SCAN (non-blocking).

    Replaces dangerous KEYS command which blocks Redis on large keyspaces.
    SCAN iterates in batches of 100, safe for production use.

    Args:
        prefix: Key prefix pattern (e.g. 'llm_cache:')

    Returns:
        Number of keys deleted.
    """
    r = get_async_redis()
    if not r:
        return 0
    cleared = 0
    try:
        cursor = 0
        pattern = f"{prefix}*"
        while True:
            cursor, keys = await r.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                cleared += await r.delete(*keys)
            if cursor == 0:
                break
    except Exception as e:
        logger.warning("clear_cache_by_prefix failed: %s", e)
    return cleared


async def get_cached_with_semantic(
    query: str,
    model: str = "qwen3.6-flash",
    temperature: float = 0.0,
    max_tokens: int = 500,
) -> Optional[str]:
    """Two-layer cache lookup: exact → semantic.

    Layer 1: Exact match via token-bag hash (fastest, <1ms)
    Layer 2: Semantic similarity search via embedding (medium, ~10ms)
    Returns None on miss.

    Metrics: Layer 1 hits/misses tracked in metrics module.
    Layer 2 hits/misses tracked in semantic_cache._stats (no double-counting).

    Args:
        query: User query text
        model: LLM model name
        temperature: Sampling temperature
        max_tokens: Maximum tokens to generate

    Returns:
        Cached response or None if miss
    """
    start_time = time.monotonic()

    # Layer 1: Exact cache (fastest) — tracked in metrics module
    exact_result = await get_cached(query)
    if exact_result is not None:
        latency_ms = (time.monotonic() - start_time) * 1000
        record_hit("exact", latency_ms)
        logger.debug("Two-layer cache: exact HIT for query")
        return exact_result

    # Layer 2: Semantic cache — tracked internally by semantic_cache._stats
    sem_cache = get_semantic_cache_instance()
    tenant_id = get_current_tenant_id()
    if sem_cache:
        try:
            result = await sem_cache.get_exact(
                query=query,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                tenant_id=tenant_id,
            )
            if result is not None:
                logger.debug("Two-layer cache: semantic EXACT HIT")
                return result

            # Try semantic similarity search
            sem_result = await sem_cache.get_semantic(
                query=query,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if sem_result is not None:
                response, score = sem_result
                logger.debug(
                    "Two-layer cache: semantic SIMILAR HIT (score=%.3f)", score
                )
                # Populate exact cache for future lookups
                await set_cached(query, response)
                return response
        except Exception as e:
            latency_ms = (time.monotonic() - start_time) * 1000
            record_error()
            logger.debug("Semantic cache lookup error: %s (falling back to miss)", e)

    # Cache miss — record once in metrics
    latency_ms = (time.monotonic() - start_time) * 1000
    record_miss(latency_ms)
    return None


async def set_cached_with_semantic(
    query: str,
    response: str,
    model: str = "qwen3.6-flash",
    temperature: float = 0.0,
    max_tokens: int = 500,
    ttl: int = 3600,
):
    """Store response in both exact and semantic caches.

    Layer 1: Store in exact cache (hash-based, for instant lookup)
    Layer 2: Store in semantic cache (embedding-based, for similar queries)

    Args:
        query: User query text
        response: LLM response to cache
        model: LLM model name
        temperature: Sampling temperature
        max_tokens: Maximum tokens to generate
        ttl: Time-to-live in seconds (default: 3600 = 1 hour)
    """
    # Store in exact cache (always works, even without semantic module)
    await set_cached(query, response, ttl)
    record_set()

    # Store in semantic cache (may be unavailable)
    sem_cache = get_semantic_cache_instance()
    tenant_id = get_current_tenant_id()
    if sem_cache:
        try:
            await sem_cache.set(
                query=query,
                response=response,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                ttl=ttl,
                tenant_id=tenant_id,
            )
            logger.debug("Stored response in semantic cache")
        except Exception as e:
            logger.debug("Semantic cache store error: %s (non-fatal)", e)
            record_error()


# Re-export for backward compatibility
__all__ = [
    # Connection
    "get_async_redis",
    "get_sync_redis",
    "close_sync_redis",
    "close_async_redis",
    "get_redis",
    "close_redis",
    # Exact cache
    "get_cached",
    "set_cached",
    "mem_get",
    "mem_set",
    "_mem_cache_key",
    "_mem_cache",
    # Metrics
    "get_metrics",
    "record_hit",
    "record_miss",
    "record_set",
    "record_error",
    # Semantic cache integration
    "get_semantic_cache_instance",
    "increment_cache_miss",
    "get_cache_metrics",
    "semantic_cache_key",
    "clear_cache_by_prefix",
    "get_cached_with_semantic",
    "set_cached_with_semantic",
]
