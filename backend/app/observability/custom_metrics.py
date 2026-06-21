"""Custom Prometheus metrics for Aureon platform.

Provides cache, database, SSE streaming, and WebSocket metrics
that complement the existing prometheus-fastapi-instrumentator auto metrics.
"""
from prometheus_client import Counter, Histogram, Gauge

# Cache metrics
cache_lookups_total = Counter(
    "cache_lookups_total",
    "Total cache lookups",
    ["type"],  # exact, semantic, miss
)
cache_latency_seconds = Histogram(
    "cache_latency_seconds",
    "Cache lookup latency in seconds",
    ["type"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.5],
)

# Database pool metrics
db_pool_size = Gauge("db_pool_size", "DB connection pool total size")
db_pool_idle = Gauge("db_pool_idle", "DB connection pool idle connections")

# SSE streaming metrics
sse_chunks_per_response = Histogram(
    "sse_chunks_per_response",
    "Number of SSE chunks per streaming response",
    buckets=[10, 50, 100, 200, 500, 1000, 5000],
)

# WebSocket metrics
ws_active_connections = Gauge(
    "ws_active_connections",
    "Active WebSocket connections",
    ["type"],  # chat, dashboard
)