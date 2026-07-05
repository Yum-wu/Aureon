"""Observability API Router — PostgreSQL asyncpg backend."""

from fastapi import APIRouter, Query
import structlog

from app.observability import QueryTrace

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Observability"])


async def _get_pool():
    from app.database.connection import get_db_pool
    pool = get_db_pool()
    if pool is None:
        raise RuntimeError("DATABASE_URL not configured")
    return pool


async def get_recent_traces(limit: int = 100) -> list[QueryTrace]:
    """获取最近的查询追踪"""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM query_traces ORDER BY created_at DESC LIMIT $1",
            limit,
        )

    result = []
    for row in rows:
        created_at = row.get("created_at")
        if hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()

        result.append(QueryTrace(
            id=row["id"],
            request_id=row["request_id"],
            session_id=row.get("session_id"),
            user_id=row.get("user_id"),
            workspace_id=row.get("workspace_id"),
            query=row["query"],
            retrieval_latency_ms=row.get("retrieval_latency_ms", 0),
            rerank_latency_ms=row.get("rerank_latency_ms", 0),
            llm_latency_ms=row.get("llm_latency_ms", 0),
            total_latency_ms=row.get("latency_ms", 0),
            cache_hit=bool(row.get("cache_hit", False)),
            status="completed",
            created_at=created_at,
        ))
    return result


async def get_trace_stats() -> dict:
    """获取追踪统计数据"""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM query_traces") or 0
        cache_hits = await conn.fetchval("SELECT COUNT(*) FROM query_traces WHERE cache_hit = TRUE") or 0

        avg_total = await conn.fetchval("SELECT AVG(latency_ms) FROM query_traces") or 0.0
        avg_retrieval = await conn.fetchval("SELECT AVG(retrieval_latency_ms) FROM query_traces") or 0.0
        avg_llm = await conn.fetchval("SELECT AVG(llm_latency_ms) FROM query_traces") or 0.0

        p95_total = await conn.fetchval(
            """
            SELECT latency_ms FROM query_traces
            ORDER BY latency_ms
            LIMIT 1 OFFSET (SELECT GREATEST(0, CAST(COUNT(*) * 0.95 AS INTEGER) - 1) FROM query_traces)
            """
        ) or 0.0

    return {
        "total_requests": total,
        "success_count": total,
        "failed_count": 0,
        "success_rate": 100.0 if total > 0 else 0,
        "cache_hit_rate": (cache_hits / total * 100) if total > 0 else 0,
        "avg_total_latency_ms": round(avg_total, 2),
        "avg_retrieval_latency_ms": round(avg_retrieval, 2),
        "avg_llm_latency_ms": round(avg_llm, 2),
        "p95_total_latency_ms": round(p95_total, 2),
        "total_tokens_input": 0,
        "total_tokens_output": 0,
    }


# ── Endpoints ──


@router.get("/traces")
async def list_traces(limit: int = Query(100, ge=1, le=1000)):
    """获取最近的查询追踪"""
    traces = await get_recent_traces(limit)
    return {"traces": traces, "count": len(traces)}


@router.get("/stats")
async def observability_stats():
    """获取可观测性统计数据"""
    return await get_trace_stats()


@router.get("/prompts")
async def list_prompts():
    """获取所有缓存的提示词（用于调试/管理）"""
    from app.observability.prompt_manager import get_all_prompts

    prompts = get_all_prompts()
    return {
        name: value[:100] + "..." if len(value) > 100 else value
        for name, value in prompts.items()
    }


@router.post("/prompts/refresh")
async def refresh_prompts_endpoint():
    """手动从 LangFuse 刷新所有提示词"""
    from app.observability.prompt_manager import refresh_prompts

    count = await refresh_prompts()
    return {"refreshed": count}
