"""RAG 系统统计 + 文档管理 API — Dashboard / Documents 数据源"""
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..dependencies import get_redis_or_none
from ..exceptions import AureonException, RedisUnavailableError, VectorStoreError
from ..rag.vector_store import get_collection_stats

logger = logging.getLogger(__name__)

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

    # Real collection stats from Chroma
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
    chunk_count: int
    status: str


@router.get("/api/rag/documents")
async def get_documents():
    """List all indexed documents grouped by source from Chroma collection."""
    try:
        from ..rag.vector_store import _get_collection
        collection = _get_collection()
        total = collection.count()
        if total == 0:
            return {"documents": [], "total_docs": 0, "total_chunks": 0}

        all_data = collection.get(include=["metadatas"])
        # Group chunks by source file
        doc_map: dict[str, dict] = defaultdict(lambda: {
            "title": "", "source": "", "file_type": "md", "chunk_count": 0
        })
        for meta in all_data.get("metadatas", []):
            if not meta or not isinstance(meta, dict):
                continue
            src = meta.get("source") or meta.get("title", "unknown")
            doc = doc_map[src]
            doc["source"] = src
            doc["title"] = meta.get("title", src.replace(".md", "").replace("_", " "))
            doc["chunk_count"] += 1
            if src.endswith(".pdf"):
                doc["file_type"] = "pdf"
            elif src.endswith(".txt"):
                doc["file_type"] = "txt"

        documents = [
            DocumentItem(title=d["title"], source=d["source"], file_type=d["file_type"],
                         chunk_count=d["chunk_count"], status="ready")
            for d in sorted(doc_map.values(), key=lambda x: x["title"])
        ]
        return {"documents": [d.model_dump() for d in documents],
                "total_docs": len(documents), "total_chunks": total}
    except Exception as e:
        if isinstance(e, VectorStoreError):
            raise
        logger.warning("get_documents failed: %s", e)
        raise VectorStoreError(detail=f"Failed to fetch documents: {str(e)}")


# ── Benchmark API ──

import json
from pathlib import Path


BENCHMARK_FILE = Path(__file__).parent.parent.parent / "data" / "benchmark_results.json"


class BenchmarkData(BaseModel):
    timestamp: Optional[str] = None
    metrics: list[dict]
    services: dict[str, str]


@router.get("/api/rag/benchmark")
async def get_benchmark():
    """Read benchmark results from file — dynamic data source."""
    try:
        if BENCHMARK_FILE.exists():
            with open(BENCHMARK_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return BenchmarkData(**data)
        else:
            logger.warning("Benchmark file not found: %s", BENCHMARK_FILE)
            return BenchmarkData(metrics=[], services={})
    except Exception as e:
        logger.error("Failed to read benchmark file: %s", e)
        raise AureonException(status_code=500, error_type="benchmark_read_error", detail=str(e))


# ── Query Volume API ──


@router.get("/api/rag/query-volume")
async def get_query_volume(days: int = 7):
    """Get daily query counts for the last N days."""
    redis = get_redis_or_none()

    if not redis:
        # In-memory fallback: generate mock data for demo
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
        last_synced=None,  # TODO: track last sync time
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

    # TODO: Implement actual blog sync logic
    # This would fetch articles from the blog and index them into Chroma
    return {
        "status": "success",
        "message": "Blog sync endpoint ready — implementation pending",
        "blog_url": settings.blog_url,
    }
