# -*- coding: utf-8 -*-
"""Cache metrics collection - hit rates, latencies, counters."""
from collections import deque
import structlog

logger = structlog.get_logger()

_cache_metrics = {
    "exact_hits": 0,
    "semantic_hits": 0,
    "misses": 0,
    "sets": 0,
    "errors": 0,
    "latencies": deque(maxlen=1000),
    "total_lookups": 0,
}


def record_hit(hit_type: str, latency_ms: float) -> None:
    """Record cache hit (exact or semantic)."""
    _cache_metrics[f"{hit_type}_hits"] += 1
    _cache_metrics["total_lookups"] += 1
    _cache_metrics["latencies"].append(latency_ms)


def record_miss(latency_ms: float) -> None:
    """Record cache miss."""
    _cache_metrics["misses"] += 1
    _cache_metrics["total_lookups"] += 1
    _cache_metrics["latencies"].append(latency_ms)


def record_set() -> None:
    """Record cache set."""
    _cache_metrics["sets"] += 1


def record_error() -> None:
    """Record cache error."""
    _cache_metrics["errors"] += 1


def get_metrics() -> dict:
    """Return snapshot of current cache metrics."""
    latencies = list(_cache_metrics["latencies"])
    return {
        "exact_hits": _cache_metrics["exact_hits"],
        "semantic_hits": _cache_metrics["semantic_hits"],
        "misses": _cache_metrics["misses"],
        "sets": _cache_metrics["sets"],
        "errors": _cache_metrics["errors"],
        "total_lookups": _cache_metrics["total_lookups"],
        "hit_rate": (
            (_cache_metrics["exact_hits"] + _cache_metrics["semantic_hits"])
            / max(_cache_metrics["total_lookups"], 1)
        ),
        "avg_latency_ms": sum(latencies) / max(len(latencies), 1),
        "p95_latency_ms": sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0,
    }
