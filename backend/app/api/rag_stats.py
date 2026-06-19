"""RAG 系统统计 + 文档管理 API — Dashboard / Documents 数据源"""
import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
import structlog

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..dependencies import get_redis_or_none
from ..exceptions import AureonException, VectorStoreError
from ..rag.vector_store import get_collection_stats

logger = structlog.get_logger()

router = APIRouter()

class RecentQuery(BaseModel):
    query: str
    sources_count: int
    latency_ms: float
    timestamp: str

class StatsResponse(BaseModel):
    cache_hit_rate: float
    query_count_24h: int
    avg_retrieval_latency_ms: float
    total_indexed_docs: int
    total_chunks: int


class RecentQueriesResponse(BaseModel):
    queries: list[RecentQuery]


STATS_PREFIX = "aureon:stats"

# In-memory fallback when Redis is unavailable
_mem_queries: list[dict] = []
_mem_count: int = 0
_mem_latencies: list[float] = []
_MEM_MAX = 100


async def record_query(
    query: str,
    sources_count: int,
    latency_ms: float,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """记录一次查询（由 RAG API 调用）

    优先 Redis，无 Redis 时降级到内存缓存。

    Args:
        query: 用户查询
        sources_count: 引用源数量
        latency_ms: 延迟（毫秒）
        input_tokens: 输入 token 数
        output_tokens: 输出 token 数
    """
    redis = get_redis_or_none()
    now = datetime.now(timezone.utc)
    timestamp = now.isoformat()

    # Verify Redis is actually connected before using it
    if redis:
        try:
            await redis.ping()
        except Exception:
            redis = None  # Not connected, use in-memory

    # In-memory fallback when Redis is unavailable
    if not redis:
        logger.info("record_query: using in-memory fallback (redis=%s)", redis)
        global _mem_count, _mem_queries, _mem_latencies
        _mem_count += 1
        _mem_queries.insert(0, {
            "query": query, "sources_count": sources_count,
            "latency_ms": latency_ms, "timestamp": timestamp,
        })
        _mem_queries = _mem_queries[:_MEM_MAX]
        _mem_latencies.append(latency_ms)
        if len(_mem_latencies) > _MEM_MAX:
            _mem_latencies = _mem_latencies[-_MEM_MAX:]
        return
    # Fire-and-forget PostgreSQL persistence (non-blocking)
    try:
        import asyncio
        asyncio.create_task(_persist_to_pg(
            query=query,
            sources_count=sources_count,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            intent=_classify_intent(query),
        ))
    except Exception as pg_err:
        logger.debug("PG persist skipped: %s", pg_err)

    member = f"{timestamp}:{uuid.uuid4().hex[:8]}"

    try:
        async with redis.pipeline(transaction=False) as pipe:
            # 查询计数（24h 过期）
            pipe.incr(f"{STATS_PREFIX}:count_24h")
            pipe.expire(f"{STATS_PREFIX}:count_24h", 86400)

            # 最近查询列表（保留最近 100 条）
            entry = f"{timestamp}|{query}|{sources_count}|{latency_ms}"
            pipe.lpush("aureon:queries:recent", entry)
            pipe.ltrim("aureon:queries:recent", 0, 99)

            # 延迟聚合（score = latency_ms, member = timestamp:uuid）
            pipe.zadd(f"{STATS_PREFIX}:latencies:z", {member: latency_ms})
            # Remove entries with score > 60000 (stale timestamp-based entries)
            pipe.zremrangebyscore(f"{STATS_PREFIX}:latencies:z", 60000, "+inf")
            # Keep only last 500 entries
            pipe.zremrangebyrank(f"{STATS_PREFIX}:latencies:z", 0, -501)

            # Token 使用统计
            if input_tokens > 0 or output_tokens > 0:
                date_key = now.strftime("%Y-%m-%d")
                pipe.hincrby(f"{STATS_PREFIX}:tokens:{date_key}", "input", input_tokens)
                pipe.hincrby(f"{STATS_PREFIX}:tokens:{date_key}", "output", output_tokens)
                pipe.hincrby(f"{STATS_PREFIX}:tokens:{date_key}", "queries", 1)
                pipe.expire(f"{STATS_PREFIX}:tokens:{date_key}", 86400 * 7)  # 保留 7 天

            # 按小时统计查询量
            hour_key = now.strftime("%Y-%m-%d-%H")
            pipe.incr(f"{STATS_PREFIX}:hourly:{hour_key}")
            pipe.expire(f"{STATS_PREFIX}:hourly:{hour_key}", 86400 * 2)  # 保留 2 天

            # 按意图分类统计
            intent = _classify_intent(query)
            pipe.hincrby(f"{STATS_PREFIX}:intents", intent, 1)

            await pipe.execute()
    except Exception as e:
        logger.warning("record_query pipeline failed: %s", e)
        # Fall back to in-memory on Redis failure
        _mem_count += 1
        _mem_queries.insert(0, {
            "query": query, "sources_count": sources_count,
            "latency_ms": latency_ms, "timestamp": timestamp,
        })
        _mem_queries = _mem_queries[:_MEM_MAX]
        _mem_latencies.append(latency_ms)
        if len(_mem_latencies) > _MEM_MAX:
            _mem_latencies = _mem_latencies[-_MEM_MAX:]


async def _persist_to_pg(
    *,
    query: str,
    sources_count: int,
    latency_ms: float,
    input_tokens: int,
    output_tokens: int,
    intent: str,
) -> None:
    """Background task: persist query event to PostgreSQL."""
    try:
        from app.api.analytics_store import persist_query_event, upsert_daily_aggregate

        await persist_query_event(
            query_text=query,
            sources_count=sources_count,
            latency_ms=latency_ms,
            tokens_in=input_tokens,
            tokens_out=output_tokens,
            intent=intent,
        )
        await upsert_daily_aggregate(
            latency_ms=latency_ms,
            tokens_in=input_tokens,
            tokens_out=output_tokens,
        )
    except Exception as exc:
        logger.warning("pg_persist_failed: %s", exc)


def _classify_intent(query: str) -> str:
    """简单意图分类"""
    query_lower = query.lower()
    if any(kw in query_lower for kw in ["代码", "code", "函数", "function", "api", "实现"]):
        return "code_search"
    elif any(kw in query_lower for kw in ["文档", "document", "上传", "管理", "列表"]):
        return "document_query"
    else:
        return "general_qa"


@router.get("/api/rag/stats", response_model=StatsResponse)
async def get_stats(redis=Depends(get_redis_or_none)):
    count = 0
    avg_latency = 0.0
    hit_rate = 0.0

    if redis:
        try:
            count = int(await redis.get(f"{STATS_PREFIX}:count_24h") or 0)

            # Latencies: get scores from sorted set (score = latency_ms)
            latencies_raw = await redis.zrange(
                f"{STATS_PREFIX}:latencies:z", 0, -1, withscores=True
            )
            latencies = []
            for member, score in latencies_raw:
                try:
                    latencies.append(float(score))
                except (ValueError, TypeError):
                    pass  # skip malformed entries

            # Fallback: if sorted set empty, read from recent queries list
            if not latencies:
                recent_entries = await redis.lrange("aureon:queries:recent", 0, 99)
                for entry in recent_entries:
                    parts = entry.split("|", 3)
                    if len(parts) == 4:
                        try:
                            latencies.append(float(parts[3]))
                        except (ValueError, TypeError):
                            pass

            avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

            cache_hits = int(await redis.get(f"{STATS_PREFIX}:cache_hits") or 0)
            cache_misses = int(await redis.get(f"{STATS_PREFIX}:cache_misses") or 0)
            total = cache_hits + cache_misses
            hit_rate = cache_hits / total if total > 0 else 0.0
        except Exception as e:
            if isinstance(e, AureonException):
                raise
            logger.warning("get_stats redis_read_failed: %s", e)
    else:
        # In-memory fallback
        count = _mem_count
        avg_latency = sum(_mem_latencies) / len(_mem_latencies) if _mem_latencies else 0.0

    # Real collection stats from vector store
    doc_count = 0
    chunk_count = 0
    try:
        doc_count, chunk_count = get_collection_stats()
    except Exception as e:
        logger.warning("get_stats vector_store_failed: %s", e)

    return StatsResponse(
        cache_hit_rate=round(hit_rate, 4),
        query_count_24h=count,
        avg_retrieval_latency_ms=round(avg_latency, 1),
        total_indexed_docs=doc_count,
        total_chunks=chunk_count,
    )


@router.get("/api/rag/queries/recent", response_model=RecentQueriesResponse)
async def get_recent_queries(limit: int = Query(5, ge=1, le=50), redis=Depends(get_redis_or_none)):
    queries = []

    if not redis:
        # In-memory fallback
        for q in _mem_queries[:limit]:
            queries.append(RecentQuery(**q))
        return {"queries": queries}

    try:
        entries = await redis.lrange("aureon:queries:recent", 0, limit - 1)
        for entry in entries:
            parts = entry.split("|", 3)
            if len(parts) == 4:
                queries.append(RecentQuery(
                    query=parts[1],
                    sources_count=int(parts[2]),
                    latency_ms=float(parts[3]),
                    timestamp=parts[0],
                ))
    except Exception as e:
        if isinstance(e, AureonException):
            raise
        logger.warning("get_recent_queries redis_read_failed: %s", e)

    return {"queries": queries}


# ── Documents API ──


class DocumentItem(BaseModel):
    title: str
    source: str
    file_type: str
    language: str = "unknown"
    chunk_count: int
    status: str


@router.get("/api/rag/documents")
async def get_documents():
    """List all indexed documents from Qdrant vector store."""
    try:
        return _get_documents_qdrant()
    except Exception as e:
        if isinstance(e, VectorStoreError):
            raise
        logger.warning("get_documents failed: %s", e)
        raise VectorStoreError(detail=f"Failed to fetch documents: {str(e)}")


def _get_documents_qdrant():
    """Qdrant implementation of get_documents."""
    from ..rag.vector_store import _get_qdrant, _get_qdrant_collection_name
    client = _get_qdrant()
    collection_name = _get_qdrant_collection_name()
    try:
        info = client.get_collection(collection_name)
        total = info.points_count or 0
    except Exception as e:
        raise VectorStoreError(detail=f"Qdrant collection error: {str(e)}")

    if total == 0:
        return {"documents": [], "total_docs": 0, "total_chunks": 0}

    doc_map: dict[str, dict] = defaultdict(lambda: {
        "title": "", "source": "", "file_type": "md", "language": "unknown", "chunk_count": 0
    })
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection_name,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for pt in points:
            meta = pt.payload.get("metadata", {}) if pt.payload else {}
            if not meta or not isinstance(meta, dict):
                continue
            src = meta.get("source") or meta.get("title", "unknown")
            doc = doc_map[src]
            doc["source"] = src
            doc["title"] = meta.get("title", src.replace(".md", "").replace("_", " "))
            doc["chunk_count"] += 1
            doc["language"] = meta.get("language", "unknown")
            if src.endswith(".pdf"):
                doc["file_type"] = "pdf"
            elif src.endswith(".docx"):
                doc["file_type"] = "docx"
            elif src.endswith(".xlsx") or src.endswith(".xls"):
                doc["file_type"] = "xlsx"
            elif src.endswith(".txt"):
                doc["file_type"] = "txt"
        if offset is None:
            break

    documents = [
        DocumentItem(title=d["title"], source=d["source"], file_type=d["file_type"],
                     language=d["language"], chunk_count=d["chunk_count"], status="ready")
        for d in sorted(doc_map.values(), key=lambda x: x["title"])
    ]
    return {"documents": [d.model_dump() for d in documents],
            "total_docs": len(documents), "total_chunks": total}



# ── Benchmark API ──


BENCHMARK_FILE = Path(__file__).parent.parent.parent / "data" / "benchmark_results.json"


class BenchmarkData(BaseModel):
    timestamp: Optional[str] = None
    metrics: list[dict]
    services: dict[str, str]


@router.get("/api/rag/benchmark")
async def get_benchmark():
    """Read benchmark results from file — dynamic data source."""
    if not BENCHMARK_FILE.exists():
        logger.warning("Benchmark file not found: %s", BENCHMARK_FILE)
        return BenchmarkData(metrics=[], services={})
    try:
        with open(BENCHMARK_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return BenchmarkData(**data)
    except (UnicodeDecodeError, json.JSONDecodeError, OSError) as e:
        logger.error("Benchmark file corrupted or unreadable: %s", e)
        return BenchmarkData(metrics=[], services={})


# ── Query Volume API ──


@router.get("/api/rag/query-volume")
async def get_query_volume(days: int = 7):
    """Get daily query counts for the last N days."""
    redis = get_redis_or_none()

    if not redis:
        # PostgreSQL fallback (survives redeployment)
        from app.api.analytics_store import get_daily_volumes
        pg_data = await get_daily_volumes(days=days)
        if pg_data:
            total = sum(d["count"] for d in pg_data)
            return {"data": pg_data, "total": total}
        # PG also empty — return zero-filled structure
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        data = []
        for i in range(days - 1, -1, -1):
            date = now - timedelta(days=i)
            data.append({
                "date": date.strftime("%Y-%m-%d"),
                "count": 0
            })
        return {"data": data, "total": 0}

    try:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        daily_counts = {}

        # Aggregate hourly counts into daily counts
        for i in range(days):
            date = now - timedelta(days=i)
            date_key = date.strftime("%Y-%m-%d")
            daily_counts[date_key] = 0

            # Sum all hourly keys for this date
            for hour in range(24):
                hour_key = f"{date_key}-{hour:02d}"
                count = await redis.get(f"{STATS_PREFIX}:hourly:{hour_key}")
                if count:
                    daily_counts[date_key] += int(count)

        # Convert to list sorted by date ascending
        data = [
            {"date": date_key, "count": daily_counts[date_key]}
            for date_key in sorted(daily_counts.keys())
        ]

        total = sum(d["count"] for d in data)
        return {"data": data, "total": total}

    except Exception as e:
        logger.error("Error fetching query volume: %s", e)
        return {"data": [], "total": 0}


# ── Cache Analytics API ──


class CacheAnalyticsResponse(BaseModel):
    """Cache performance analytics response."""
    exact_hits: int
    semantic_hits: int
    misses: int
    total_lookups: int
    hit_rate: float
    exact_hit_rate: float
    semantic_hit_rate: float
    sets: int
    errors: int
    avg_latency_ms: float
    p50_latency_ms: float
    p90_latency_ms: float
    p99_latency_ms: float
    error_rate: float
    latency_sample_size: int
    semantic_cache_available: bool
    semantic_cache_stats: Optional[Dict[str, Any]] = None


@router.get("/api/rag/analytics/cache", response_model=CacheAnalyticsResponse)
async def cache_analytics():
    """Cache performance analytics endpoint.

    Returns detailed metrics on the two-layer cache system:
    - Exact cache (hash-based) hit rates
    - Semantic cache (vector-based) hit rates
    - Overall cache performance
    - Latency percentiles (p50, p90, p99)
    - Error rates
    - Semantic cache availability and configuration
    """
    from app.cache.redis_client import get_cache_metrics, get_semantic_cache_instance

    # Get basic cache metrics with latency data
    metrics = get_cache_metrics()

    # Check semantic cache availability
    sem_cache = get_semantic_cache_instance()
    sem_cache_available = sem_cache is not None
    sem_cache_stats = None

    # Get semantic cache stats if available
    if sem_cache:
        try:
            sem_cache_stats = await sem_cache.get_stats()
        except Exception as e:
            logger.debug("Failed to fetch semantic cache stats: %s", e)
            sem_cache_stats = {"error": str(e)}

    return CacheAnalyticsResponse(
        exact_hits=metrics.get("exact_hits", 0),
        semantic_hits=metrics.get("semantic_hits", 0),
        misses=metrics.get("misses", 0),
        total_lookups=metrics.get("total_lookups", 0),
        hit_rate=metrics.get("hit_rate", 0.0),
        exact_hit_rate=metrics.get("exact_hit_rate", 0.0),
        semantic_hit_rate=metrics.get("semantic_hit_rate", 0.0),
        sets=metrics.get("sets", 0),
        errors=metrics.get("errors", 0),
        avg_latency_ms=metrics.get("avg_latency_ms", 0.0),
        p50_latency_ms=metrics.get("p50_latency_ms", 0.0),
        p90_latency_ms=metrics.get("p90_latency_ms", 0.0),
        p99_latency_ms=metrics.get("p99_latency_ms", 0.0),
        error_rate=metrics.get("error_rate", 0.0),
        latency_sample_size=metrics.get("latency_sample_size", 0),
        semantic_cache_available=sem_cache_available,
        semantic_cache_stats=sem_cache_stats,
    )


# ── Blog Sync API ──

class BlogConfig(BaseModel):
    url: str
    sync_enabled: bool
    last_synced: Optional[str] = None


@router.get("/api/rag/blog/config")
async def get_blog_config():
    """Get blog sync configuration from settings."""
    from ..config import settings
    return BlogConfig(
        url=settings.blog_url,
        sync_enabled=settings.blog_sync_enabled,
        last_synced=None,  # 待实现：追踪最后同步时间
    )


@router.post("/api/rag/blog/sync")
async def sync_blog_documents():
    """Sync documents from external blog. Placeholder for future implementation."""
    from ..config import settings

    if not settings.blog_sync_enabled or not settings.blog_url:
        raise AureonException(
            status_code=400,
            error_type="blog_sync_disabled",
            detail="Blog sync is not enabled. Set BLOG_URL and BLOG_SYNC_ENABLED=true in .env",
        )

    # 待实现：Blog 同步逻辑
    # This would fetch articles from the blog and index them into the vector store
    return {
        "status": "success",
        "message": "Blog sync endpoint ready — implementation pending",
        "blog_url": settings.blog_url,
    }
