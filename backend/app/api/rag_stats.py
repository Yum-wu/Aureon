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

    # In-memory fallback when Redis is unavailable
    if not redis:
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

            # 延迟聚合（用于计算 avg/p95/p99）
            pipe.zadd(f"{STATS_PREFIX}:latencies:z", {member: latency_ms})
            # 保留最近 24h 的数据
            cutoff = (now.timestamp() - 86400)
            pipe.zremrangebyscore(f"{STATS_PREFIX}:latencies:z", 0, cutoff)

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

            # Latencies stored as sorted set by record_query via zadd
            now = datetime.now(timezone.utc)
            cutoff = now.timestamp() - 86400
            latencies = await redis.zrangebyscore(
                f"{STATS_PREFIX}:latencies:z", min=cutoff, max="+inf"
            )
            latencies = [float(l) for l in latencies]
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
