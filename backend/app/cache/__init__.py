"""Cache module - exact match + semantic + metrics."""
from app.cache.redis_client import (
    get_cached,
    set_cached,
    get_async_redis,
    get_sync_redis,
    close_sync_redis,
    close_redis,
    get_redis,
    get_metrics,
    get_cache_metrics,
    clear_cache_by_prefix,
    get_cached_with_semantic,
    set_cached_with_semantic,
    increment_cache_miss,
    _mem_cache,
)
from app.cache.semantic_cache import (
    SemanticLLMCache,
    get_semantic_cache,
    close_semantic_cache,
)

__all__ = [
    # Exact cache
    "get_cached",
    "set_cached",
    # Connection
    "get_async_redis",
    "get_sync_redis",
    "close_sync_redis",
    "close_redis",
    "get_redis",
    # Metrics
    "get_metrics",
    "get_cache_metrics",
    # Semantic cache
    "SemanticLLMCache",
    "get_semantic_cache",
    "close_semantic_cache",
    # Utilities
    "clear_cache_by_prefix",
    "get_cached_with_semantic",
    "set_cached_with_semantic",
    "increment_cache_miss",
    "_mem_cache",
]
