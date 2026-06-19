"""Analytics PostgreSQL persistence layer.

Provides durable storage for query metrics that survives redeployment.
Redis remains the hot-path cache; PostgreSQL is the source of truth
for historical data.

Write path:  rag_stats.record_query() -> Redis (fast) + PG (durable)
Read path:   analytics.py -> Redis first -> PG fallback when Redis empty
"""

from datetime import datetime, timezone, timedelta
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def persist_query_event(
    *,
    tenant_id: str = "default",
    query_text: str = "",
    sources_count: int = 0,
    latency_ms: float = 0,
    tokens_in: int = 0,
    tokens_out: int = 0,
    intent: str = "general_qa",
    cache_hit: bool = False,
    error: bool = False,
) -> None:
    """Write a single query event to PostgreSQL.

    Called from ``rag_stats.record_query`` after the Redis write.
    Failures are logged but never raised - analytics persistence must
    not break the main query path.
    """
    from app.database.connection import get_db_pool

    pool = get_db_pool()
    if pool is None:
        return

    try:
        await pool.execute(
            """
            INSERT INTO analytics_events
                (tenant_id, event_type, query_text, sources_count,
                 latency_ms, tokens_in, tokens_out, intent, cache_hit, error)
            VALUES ($1, 'query', $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            tenant_id,
            query_text[:500] if query_text else "",
            sources_count,
            latency_ms,
            tokens_in,
            tokens_out,
            intent,
            cache_hit,
            error,
        )
    except Exception as exc:
        logger.warning("analytics_pg_write_failed", error=str(exc))


async def upsert_daily_aggregate(
    *,
    tenant_id: str = "default",
    latency_ms: float = 0,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cache_hit: bool = False,
    error: bool = False,
) -> None:
    """Upsert the daily aggregate row in ``analytics_daily``.

    Uses ``INSERT ... ON CONFLICT DO UPDATE`` for atomicity.
    """
    from app.database.connection import get_db_pool

    pool = get_db_pool()
    if pool is None:
        return

    today = datetime.now(timezone.utc).date()
    try:
        await pool.execute(
            """
            INSERT INTO analytics_daily
                (tenant_id, date, total_queries, errors, cache_hits,
                 tokens_in, tokens_out, avg_latency_ms, updated_at)
            VALUES ($1, $2, 1,
                    CASE WHEN $3 THEN 1 ELSE 0 END,
                    CASE WHEN $4 THEN 1 ELSE 0 END,
                    $5, $6, $7, NOW())
            ON CONFLICT (tenant_id, date) DO UPDATE SET
                total_queries   = analytics_daily.total_queries + 1,
                errors          = analytics_daily.errors + CASE WHEN $3 THEN 1 ELSE 0 END,
                cache_hits      = analytics_daily.cache_hits + CASE WHEN $4 THEN 1 ELSE 0 END,
                tokens_in       = analytics_daily.tokens_in + $5,
                tokens_out      = analytics_daily.tokens_out + $6,
                avg_latency_ms  = (analytics_daily.avg_latency_ms * analytics_daily.total_queries + $7)
                                  / (analytics_daily.total_queries + 1),
                updated_at      = NOW()
            """,
            tenant_id,
            today,
            error,
            cache_hit,
            tokens_in,
            tokens_out,
            latency_ms,
        )
    except Exception as exc:
        logger.warning("analytics_daily_upsert_failed", error=str(exc))


async def get_usage_from_pg(
    *,
    tenant_id: str = "default",
    days: int = 1,
) -> dict[str, Any]:
    """Read usage analytics from PostgreSQL.

    Returns the same shape as the Redis-backed ``/analytics/usage`` endpoint.
    """
    from app.database.connection import get_db_pool

    pool = get_db_pool()
    if pool is None:
        return {"total": 0, "perHour": 0, "byIntent": {}}

    since = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        row = await pool.fetchrow(
            "SELECT COUNT(*) AS total FROM analytics_events WHERE tenant_id=$1 AND created_at >= $2",
            tenant_id,
            since,
        )
        total = row["total"] if row else 0
        hours = max(days * 24, 1)
        per_hour = round(total / hours, 1)

        # Intent breakdown
        intent_rows = await pool.fetch(
            """
            SELECT intent, COUNT(*) AS cnt
            FROM analytics_events
            WHERE tenant_id=$1 AND created_at >= $2
            GROUP BY intent
            """,
            tenant_id,
            since,
        )
        by_intent = {r["intent"]: int(r["cnt"]) for r in intent_rows}

        return {"total": total, "perHour": per_hour, "byIntent": by_intent}
    except Exception as exc:
        logger.warning("analytics_pg_usage_read_failed", error=str(exc))
        return {"total": 0, "perHour": 0, "byIntent": {}}


async def get_latency_from_pg(
    *,
    tenant_id: str = "default",
    days: int = 1,
) -> dict[str, Any]:
    """Read latency analytics from PostgreSQL."""
    from app.database.connection import get_db_pool

    pool = get_db_pool()
    if pool is None:
        return {"avg": 0, "p95": 0, "p99": 0}

    since = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        rows = await pool.fetch(
            """
            SELECT latency_ms FROM analytics_events
            WHERE tenant_id=$1 AND created_at >= $2 AND latency_ms > 0
            ORDER BY latency_ms
            """,
            tenant_id,
            since,
        )
        if not rows:
            return {"avg": 0, "p95": 0, "p99": 0}

        latencies = [r["latency_ms"] for r in rows]
        n = len(latencies)
        avg = sum(latencies) / n
        p95 = latencies[min(int(n * 0.95), n - 1)]
        p99 = latencies[min(int(n * 0.99), n - 1)]

        return {"avg": round(avg, 1), "p95": round(p95, 1), "p99": round(p99, 1)}
    except Exception as exc:
        logger.warning("analytics_pg_latency_read_failed", error=str(exc))
        return {"avg": 0, "p95": 0, "p99": 0}


async def get_tokens_from_pg(
    *,
    tenant_id: str = "default",
    days: int = 1,
) -> dict[str, Any]:
    """Read token usage analytics from PostgreSQL."""
    from app.database.connection import get_db_pool

    pool = get_db_pool()
    if pool is None:
        return {"input": 0, "output": 0, "total": 0, "cost": 0, "costPerQuery": 0}

    since = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        row = await pool.fetchrow(
            """
            SELECT
                COALESCE(SUM(tokens_in), 0) AS input_tokens,
                COALESCE(SUM(tokens_out), 0) AS output_tokens,
                COUNT(*) AS queries
            FROM analytics_events
            WHERE tenant_id=$1 AND created_at >= $2
            """,
            tenant_id,
            since,
        )
        input_tokens = int(row["input_tokens"]) if row else 0
        output_tokens = int(row["output_tokens"]) if row else 0
        queries = int(row["queries"]) if row else 0

        cost_per_1k_input = 0.00015
        cost_per_1k_output = 0.0006
        cost = round(
            (input_tokens / 1000 * cost_per_1k_input)
            + (output_tokens / 1000 * cost_per_1k_output),
            2,
        )
        cost_per_query = round(cost / queries, 4) if queries > 0 else 0

        return {
            "input": input_tokens,
            "output": output_tokens,
            "total": input_tokens + output_tokens,
            "cost": cost,
            "costPerQuery": cost_per_query,
        }
    except Exception as exc:
        logger.warning("analytics_pg_tokens_read_failed", error=str(exc))
        return {"input": 0, "output": 0, "total": 0, "cost": 0, "costPerQuery": 0}


async def get_daily_volumes(
    *,
    tenant_id: str = "default",
    days: int = 7,
) -> list[dict[str, Any]]:
    """Get daily query volumes from the pre-aggregated ``analytics_daily`` table."""
    from app.database.connection import get_db_pool

    pool = get_db_pool()
    if pool is None:
        return []

    since = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        rows = await pool.fetch(
            """
            SELECT date, total_queries
            FROM analytics_daily
            WHERE tenant_id=$1 AND date >= $2
            ORDER BY date ASC
            """,
            tenant_id,
            since.date(),
        )
        return [
            {"date": r["date"].isoformat(), "count": int(r["total_queries"])}
            for r in rows
        ]
    except Exception as exc:
        logger.warning("analytics_pg_daily_read_failed", error=str(exc))
        return []
