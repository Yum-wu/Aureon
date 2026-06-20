"""
Redis semantic cache for LLM responses.

Stores and retrieves LLM responses by exact query match.
Degrades gracefully when Redis is unavailable.
Falls back to in-memory dict cache when Redis is down.
"""

import hashlib
import random
import re
import time
from collections import deque
from typing import Optional, Dict, Any
import structlog
from app.multi_tenant.middleware import get_current_tenant_id

logger = structlog.get_logger()

# Sentinel: None = uninitialized, False = unavailable, valid client = ready
_redis = None

# ── In-memory fallback cache (when Redis is unavailable) ──
_mem_cache: dict = {}
_MEM_TTL = 3600  # 1 hour, same as Redis TTL
_MEM_MAX_VALUE_BYTES = 512 * 1024  # 512 KB per-value size limit


# Bump to invalidate all cached RAG responses (e.g. after retrieval logic changes)
_CACHE_VERSION = "v16"  # v16: semantic dedup via token bag


# ── Semantic cache metrics ──
_cache_metrics = {
    "exact_hits": 0,
    "semantic_hits": 0,
    "misses": 0,
    "sets": 0,
    "errors": 0,
    "latencies": deque(maxlen=1000),  # Last 1000 operations
    "total_lookups": 0,
}


def _record_cache_hit(hit_type: str, latency_ms: float):
    """Record cache hit metric.

    Args:
        hit_type: Type of hit ('exact' or 'semantic')
        latency_ms: Latency in milliseconds for this lookup
    """
    global _cache_metrics
    _cache_metrics[f"{hit_type}_hits"] += 1
    _cache_metrics["total_lookups"] += 1
    _cache_metrics["latencies"].append(latency_ms)


def _record_cache_miss(latency_ms: float):
    """Record cache miss metric.

    Args:
        latency_ms: Latency in milliseconds for this lookup
    """
    global _cache_metrics
    _cache_metrics["misses"] += 1
    _cache_metrics["total_lookups"] += 1
    _cache_metrics["latencies"].append(latency_ms)


def _mem_cache_key(key: str, tenant_id: str = "default") -> str:
    raw = key.strip().lower()
    tokens = sorted(set(re.findall(r'[\w\u4e00-\u9fff]+', raw)))
    return f"llm_cache:{_CACHE_VERSION}:{tenant_id}:{hashlib.md5(' '.join(tokens).encode()).hexdigest()}"


def _mem_get(query: str, tenant_id: str = "default") -> Optional[str]:
    """In-memory cache lookup. Checks expiry."""
    full_key = _mem_cache_key(query, tenant_id)
    entry = _mem_cache.get(full_key)
    if entry is None:
        return None
    value, expires_at = entry
    if time.monotonic() > expires_at:
        del _mem_cache[full_key]
        return None
    return value


def _mem_set(query: str, response: str, ttl: int = _MEM_TTL, tenant_id: str = "default"):
    """Store in in-memory cache with expiry + TTL jitter. Skips if value exceeds size limit.

    TTL 加随机抖动（0~300s）防止缓存雪崩：同一时刻大量缓存同时过期，
    导致请求全部穿透到后端。抖动使过期时间分散，避免集中失效。
    """
    # Skip oversized values to prevent OOM
    if len(response) > _MEM_MAX_VALUE_BYTES:
        logger.debug("In-memory cache: skipping oversized value (%d bytes)", len(response))
        return
    # TTL 随机抖动：0~300 秒，防止缓存雪崩
    jittered_ttl = ttl + (random.randint(0, 300) if ttl > 0 else 0)
    full_key = _mem_cache_key(query, tenant_id)
    _mem_cache[full_key] = (response, time.monotonic() + jittered_ttl)
    # Evict old entries if cache is too large (keep max 500)
    if len(_mem_cache) > 500:
        now = time.monotonic()
        expired = [k for k, (_, exp) in _mem_cache.items() if now > exp]
        for k in expired:
            del _mem_cache[k]
        # If still over limit, remove oldest
        if len(_mem_cache) > 500:
            oldest = sorted(_mem_cache.keys(), key=lambda k: _mem_cache[k][1])[:50]
            for k in oldest:
                del _mem_cache[k]


_redis_fail_count = 0
_RECONNECT_AFTER = 5  # Retry reconnect after N consecutive failures


# ── 同步 Redis 连接池（供后台线程使用，如 embedding 缓存） ──
_sync_redis_pool = None
_sync_redis_fail_count = 0
_SYNC_RECONNECT_AFTER = 5


def get_sync_redis():
    """返回同步 Redis 客户端单例（连接池复用），或 None 如果不可用。

    用于后台线程（如 embed_texts_llm）中无法 await 异步客户端的场景。
    使用 ConnectionPool 复用 TCP 连接，避免每次操作创建新连接。

    线程安全：redis-py 的 Redis + ConnectionPool 本身是线程安全的。
    """
    global _sync_redis_pool, _sync_redis_fail_count
    if _sync_redis_pool is not None:
        return _sync_redis_pool
    if _sync_redis_fail_count >= _SYNC_RECONNECT_AFTER:
        return None
    from app.config import settings
    if not settings.redis_url:
        # 未配置 Redis 时直接跳过，避免 fallback 到 localhost 导致连接阻塞
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
    """关闭同步 Redis 连接池，在应用 shutdown 时调用。"""
    global _sync_redis_pool
    if _sync_redis_pool is not None:
        try:
            _sync_redis_pool.connection_pool.disconnect()
        except Exception as e:
            logger.debug("redis_pool_disconnect_failed", error=str(e))
        _sync_redis_pool = None


def _get_redis():
    """Return Redis client singleton, or None if unavailable.

    Retries connection on every call when Redis was previously unavailable,
    because Redis may become available after app startup (e.g. Railway deploy).

    Sentinel values: None = unavailable/not-yet-connected, client = ready.
    """
    global _redis
    # Return cached client if available
    if _redis is not None and _redis is not False:
        return _redis
    from app.config import settings
    if not settings.redis_url:
        logger.warning("redis_url_not_configured")
        return None
    try:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        logger.info("Redis connected")
    except Exception as e:
        logger.warning("Redis unavailable (non-fatal): %s", e)
        _redis = None
    return _redis


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


async def get_cached(query: str, threshold: float = 0.92) -> Optional[str]:
    """Exact-match cache lookup. Falls back to in-memory if Redis down."""
    tenant_id = get_current_tenant_id()
    # 1. Try in-memory first (fastest, tenant-isolated)
    mem_result = _mem_get(query, tenant_id)
    if mem_result is not None:
        logger.debug("In-memory cache HIT for query hash")
        return mem_result

    # 2. Try Redis
    r = _get_redis()
    if r:
        try:
            key = await semantic_cache_key(query)
            # Add tenant prefix to key
            tenant_key = f"{tenant_id}:{key}"
            cached = await r.get(tenant_key)
            if cached is not None:
                # Also populate in-memory for faster next access
                _mem_set(query, cached, tenant_id=tenant_id)
                logger.debug("Redis cache HIT for query hash")
                return cached
        except Exception as e:
            logger.debug("Cache read error: %s", e)

    return None


async def set_cached(query: str, response: str, ttl: int = 3600):
    """Store a response in both in-memory and Redis.

    TTL 加随机抖动（0~300s）防止缓存雪崩：同一时刻大量缓存同时过期，
    导致请求全部穿透到后端。抖动使过期时间分散，避免集中失效。
    """
    tenant_id = get_current_tenant_id()
    # Always store in-memory (tenant-isolated, with TTL jitter)
    _mem_set(query, response, ttl, tenant_id=tenant_id)

    # Try Redis (TTL jitter applied independently)
    r = _get_redis()
    if not r:
        return
    try:
        key = await semantic_cache_key(query)
        # Add tenant prefix to key
        tenant_key = f"{tenant_id}:{key}"
        # Redis TTL 随机抖动：0~300 秒，防止缓存雪崩
        jittered_ttl = ttl + (random.randint(0, 300) if ttl > 0 else 0)
        await r.setex(tenant_key, jittered_ttl, response)
    except Exception as e:
        logger.debug("Cache write error: %s", e)


def get_redis():
    """Public interface for getting Redis client."""
    return _get_redis()


async def clear_cache_by_prefix(prefix: str) -> int:
    """Delete all keys matching prefix using SCAN (non-blocking).

    Replaces dangerous KEYS command which blocks Redis on large keyspaces.
    SCAN iterates in batches of 100, safe for production use.

    Args:
        prefix: Key prefix pattern (e.g. 'llm_cache:')

    Returns:
        Number of keys deleted.
    """
    r = _get_redis()
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


async def close_redis():
    """Close Redis connection on application shutdown."""
    global _redis
    if _redis:
        try:
            await _redis.close()
        except Exception as e:
            logger.debug("redis_async_close_failed", error=str(e))
        _redis = None


# ── Semantic Cache Integration ──
# Two-layer cache: exact (hash) + semantic (vector similarity)
# Gracefully degrades when SemanticLLMCache is unavailable

_semantic_cache_instance = None


def get_semantic_cache_instance():
    """Get or create SemanticLLMCache singleton.

    Lazy-loads the SemanticLLMCache module and creates a singleton instance.
    Returns None if the module is unavailable (graceful degradation).
    """
    global _semantic_cache_instance

    if _semantic_cache_instance is not None:
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
    global _cache_metrics
    _cache_metrics["misses"] += 1


def get_cache_metrics() -> Dict[str, Any]:
    """Return cache performance metrics.

    Returns:
        Dictionary with hit/miss counts, rates, and latency percentiles
    """
    global _cache_metrics

    total_lookups = _cache_metrics["total_lookups"]

    # Calculate latency percentiles from deque
    latencies = list(_cache_metrics["latencies"])
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    # Calculate percentiles efficiently
    if latencies:
        latencies_sorted = sorted(latencies)
        p50_idx = int(len(latencies_sorted) * 0.5)
        p90_idx = int(len(latencies_sorted) * 0.9)
        p99_idx = int(len(latencies_sorted) * 0.99)
        p50 = latencies_sorted[min(p50_idx, len(latencies_sorted) - 1)]
        p90 = latencies_sorted[min(p90_idx, len(latencies_sorted) - 1)]
        p99 = latencies_sorted[min(p99_idx, len(latencies_sorted) - 1)]
    else:
        p50 = p90 = p99 = 0.0

    metrics = {
        "exact_hits": _cache_metrics["exact_hits"],
        "semantic_hits": _cache_metrics["semantic_hits"],
        "misses": _cache_metrics["misses"],
        "sets": _cache_metrics["sets"],
        "errors": _cache_metrics["errors"],
        "total_lookups": total_lookups,
        "hit_rate": (
            (_cache_metrics["exact_hits"] + _cache_metrics["semantic_hits"])
            / total_lookups
            if total_lookups > 0
            else 0.0
        ),
        "exact_hit_rate": (
            _cache_metrics["exact_hits"] / total_lookups
            if total_lookups > 0
            else 0.0
        ),
        "semantic_hit_rate": (
            _cache_metrics["semantic_hits"] / total_lookups
            if total_lookups > 0
            else 0.0
        ),
        "error_rate": (
            _cache_metrics["errors"] / total_lookups
            if total_lookups > 0
            else 0.0
        ),
        "avg_latency_ms": avg_latency,
        "p50_latency_ms": p50,
        "p90_latency_ms": p90,
        "p99_latency_ms": p99,
        "latency_sample_size": len(latencies),
    }

    return metrics


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

    Metrics: Layer 1 hits/misses tracked in _cache_metrics.
    Layer 2 hits/misses tracked in semantic_cache._stats (no double-counting).

    Args:
        query: User query text
        model: LLM model name
        temperature: Sampling temperature
        max_tokens: Maximum tokens to generate

    Returns:
        Cached response or None if miss
    """
    global _cache_metrics

    start_time = time.monotonic()

    # Layer 1: Exact cache (fastest) — tracked in _cache_metrics
    exact_result = await get_cached(query)
    if exact_result is not None:
        latency_ms = (time.monotonic() - start_time) * 1000
        _record_cache_hit("exact", latency_ms)
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
            _cache_metrics["errors"] += 1
            logger.debug("Semantic cache lookup error: %s (falling back to miss)", e)

    # Cache miss — record once in _cache_metrics
    latency_ms = (time.monotonic() - start_time) * 1000
    _record_cache_miss(latency_ms)
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
    global _cache_metrics

    # Store in exact cache (always works, even without semantic module)
    await set_cached(query, response, ttl)
    _cache_metrics["sets"] += 1

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
            _cache_metrics["errors"] += 1
