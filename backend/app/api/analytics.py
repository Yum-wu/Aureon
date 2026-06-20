"""Analytics API endpoints for usage, latency, and token tracking."""

from fastapi import APIRouter, Depends, Query
from datetime import datetime, timezone
from typing import Optional
import structlog

from app.dependencies import get_redis_or_none

logger = structlog.get_logger()
router = APIRouter(prefix="/api/rag/analytics", tags=["analytics"])

STATS_PREFIX = "aureon:stats"


def _range_to_days(time_range: str) -> int:
    """Convert time range string to days."""
    mapping = {"24h": 1, "7d": 7, "30d": 30}
    return mapping.get(time_range, 1)


@router.get("/usage")
async def get_usage_analytics(
    time_range: Optional[str] = Query("24h", description="Time range: 24h, 7d, 30d"),
    redis=Depends(get_redis_or_none),
):
    """
    Get query usage analytics.

    Returns:
        - Total query count
        - Query distribution by intent
        - Queries per hour
    """
    if not redis:
        # In-memory fallback (same as /api/rag/stats when Redis is down)
        from app.api.rag_stats import _mem_count
        if _mem_count > 0:
            per_hour = round(_mem_count / 24, 1)
            return {
                "timeRange": time_range,
                "total": _mem_count,
                "perHour": per_hour,
                "byIntent": {},
                "trend": {"change": 0, "period": "vs previous period"},
                "data_available": True,
            }
        # PostgreSQL fallback (survives redeployment)
        from app.api.analytics_store import get_usage_from_pg
        pg_data = await get_usage_from_pg(days=_range_to_days(time_range))
        return {
            "timeRange": time_range,
            "total": pg_data["total"],
            "perHour": pg_data["perHour"],
            "byIntent": pg_data["byIntent"],
            "trend": {"change": 0, "period": "vs previous period"},
            "data_available": pg_data["total"] > 0,
        }

    try:
        # 总查询数
        total = int(await redis.get(f"{STATS_PREFIX}:count_24h") or 0)

        # If Redis is empty (fresh deploy), seed from PostgreSQL
        if total == 0:
            from app.api.analytics_store import get_usage_from_pg
            pg_data = await get_usage_from_pg(days=_range_to_days(time_range))
            if pg_data["total"] > 0:
                return {
                    "timeRange": time_range,
                    "total": pg_data["total"],
                    "perHour": pg_data["perHour"],
                    "byIntent": pg_data["byIntent"],
                    "trend": {"change": 0, "period": "vs previous period"},
                    "data_available": True,
                }

        # 按意图分类
        intents_raw = await redis.hgetall(f"{STATS_PREFIX}:intents")
        by_intent = {k: int(v) for k, v in intents_raw.items()} if intents_raw else {}

        # 计算每小时平均查询量
        datetime.now(timezone.utc)
        per_hour = round(total / 24, 1) if total > 0 else 0

        return {
            "timeRange": time_range,
            "total": total,
            "perHour": per_hour,
            "byIntent": by_intent,
            "trend": {
                "change": 0,  # 待实现：对比前一天数据
                "period": "vs previous period",
            },
            "data_available": total > 0,
        }
    except Exception as e:
        logger.error(f"Error fetching usage analytics: {e}")
        return {
            "timeRange": time_range,
            "total": 0,
            "perHour": 0,
            "byIntent": {},
            "trend": {"change": 0, "period": "vs previous period"},
            "data_available": False,
        }


@router.get("/latency")
async def get_latency_analytics(
    time_range: Optional[str] = Query("24h", description="Time range: 24h, 7d, 30d"),
    redis=Depends(get_redis_or_none),
):
    """
    Get latency analytics.

    Returns:
        - Average, P95, P99 latency
        - Retrieval vs LLM breakdown
        - Latency trend over time
    """
    from statistics import mean, quantiles

    if not redis:
        # In-memory fallback (same as /api/rag/stats when Redis is down)
        from app.api.rag_stats import _mem_latencies
        if _mem_latencies:
            from statistics import mean as _mean
            avg_lat = round(_mean(_mem_latencies), 1)
            max_lat = round(max(_mem_latencies), 1)
            return {
                "timeRange": time_range,
                "avg": avg_lat,
                "p95": max_lat,
                "p99": max_lat,
                "breakdown": {"retrieval": 0, "llm_first_token": 0, "llm_generation": 0},
                "trend": {"avg_change": 0, "period": "vs previous period"},
                "data_available": True,
            }
        # PostgreSQL fallback
        from app.api.analytics_store import get_latency_from_pg
        pg_data = await get_latency_from_pg(days=_range_to_days(time_range))
        return {
            "timeRange": time_range,
            "avg": pg_data["avg"],
            "p95": pg_data["p95"],
            "p99": pg_data["p99"],
            "breakdown": {
                "retrieval": 0,
                "llm_first_token": 0,
                "llm_generation": 0,
            },
            "trend": {"avg_change": 0, "period": "vs previous period"},
            "data_available": pg_data["avg"] > 0,
        }

    try:
        # 从 sorted set 获取延迟数据（score = latency_ms, member = timestamp:uuid）
        # 使用 zrange 获取所有数据（不按时间过滤，因为 score 是延迟值不是时间戳）
        latencies_raw = await redis.zrange(
            f"{STATS_PREFIX}:latencies:z", 0, -1, withscores=True
        )
        latencies = []
        for member, score in latencies_raw:
            try:
                latencies.append(float(score))
            except (ValueError, TypeError):
                pass

        if not latencies:
            # Redis empty — try PostgreSQL
            from app.api.analytics_store import get_latency_from_pg
            pg_data = await get_latency_from_pg(days=_range_to_days(time_range))
            if pg_data["avg"] > 0:
                return {
                    "timeRange": time_range,
                    "avg": pg_data["avg"],
                    "p95": pg_data["p95"],
                    "p99": pg_data["p99"],
                    "breakdown": {"retrieval": 0, "llm_first_token": 0, "llm_generation": 0},
                    "trend": {"avg_change": 0, "period": "vs previous period"},
                    "data_available": True,
                }
            return {
                "timeRange": time_range,
                "avg": 0,
                "p95": 0,
                "p99": 0,
                "breakdown": {"retrieval": 0, "llm_first_token": 0, "llm_generation": 0},
                "trend": {"avg_change": 0, "period": "vs previous period"},
                "data_available": False,
            }

        avg_lat = round(mean(latencies), 1)
        p95 = round(quantiles(latencies, n=100)[94], 1) if len(latencies) >= 100 else round(max(latencies), 1)
        p99 = round(quantiles(latencies, n=100)[98], 1) if len(latencies) >= 100 else round(max(latencies), 1)

        return {
            "timeRange": time_range,
            "avg": avg_lat,
            "p95": p95,
            "p99": p99,
            "breakdown": {
                "retrieval": 0,
                "llm_first_token": 0,
                "llm_generation": 0,
            },
            "trend": {
                "avg_change": 0,
                "period": "vs previous period",
            },
            "data_available": True,
        }
    except Exception as e:
        logger.error(f"Error fetching latency analytics: {e}")
        return {
            "timeRange": time_range,
            "avg": 0,
            "p95": 0,
            "p99": 0,
            "breakdown": {"retrieval": 0, "llm_first_token": 0, "llm_generation": 0},
            "trend": {"avg_change": 0, "period": "vs previous period"},
            "data_available": False,
        }


@router.get("/tokens")
async def get_token_analytics(
    time_range: Optional[str] = Query("24h", description="Time range: 24h, 7d, 30d"),
    redis=Depends(get_redis_or_none),
):
    """
    Get token usage analytics.

    Returns:
        - Input/output token counts
        - Estimated cost
        - Cost per query
    """
    if not redis:
        # In-memory fallback (same as /api/rag/stats when Redis is down)
        from app.api.rag_stats import _mem_count
        if _mem_count > 0:
            return {
                "timeRange": time_range,
                "input": 0,
                "output": 0,
                "total": 0,
                "cost": 0,
                "costPerQuery": 0,
                "model": "qwen3.6-flash",
                "trend": {"input_change": 0, "output_change": 0, "period": "vs previous period"},
                "data_available": False,
            }
        # PostgreSQL fallback
        from app.api.analytics_store import get_tokens_from_pg
        pg_data = await get_tokens_from_pg(days=_range_to_days(time_range))
        return {
            "timeRange": time_range,
            "input": pg_data["input"],
            "output": pg_data["output"],
            "total": pg_data["total"],
            "cost": pg_data["cost"],
            "costPerQuery": pg_data["costPerQuery"],
            "model": "qwen3.6-flash",
            "trend": {"input_change": 0, "output_change": 0, "period": "vs previous period"},
            "data_available": pg_data["total"] > 0,
        }

    try:
        # 获取今天的 token 使用
        date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        token_data = await redis.hgetall(f"{STATS_PREFIX}:tokens:{date_key}")

        input_tokens = int(token_data.get("input", 0)) if token_data else 0
        output_tokens = int(token_data.get("output", 0)) if token_data else 0
        queries = int(token_data.get("queries", 0)) if token_data else 0

        # If Redis is empty, try PostgreSQL
        if input_tokens == 0 and output_tokens == 0:
            from app.api.analytics_store import get_tokens_from_pg
            pg_data = await get_tokens_from_pg(days=_range_to_days(time_range))
            if pg_data["total"] > 0:
                return {
                    "timeRange": time_range,
                    "input": pg_data["input"],
                    "output": pg_data["output"],
                    "total": pg_data["total"],
                    "cost": pg_data["cost"],
                    "costPerQuery": pg_data["costPerQuery"],
                    "model": "qwen3.6-flash",
                    "trend": {"input_change": 0, "output_change": 0, "period": "vs previous period"},
                    "data_available": True,
                }

        # GPT-4o-mini 定价：$0.15/1M input, $0.60/1M output
        cost_per_1k_input = 0.00015
        cost_per_1k_output = 0.0006
        cost = round(
            (input_tokens / 1000 * cost_per_1k_input) + (output_tokens / 1000 * cost_per_1k_output),
            2
        )
        cost_per_query = round(cost / queries, 4) if queries > 0 else 0

        return {
            "timeRange": time_range,
            "input": input_tokens,
            "output": output_tokens,
            "total": input_tokens + output_tokens,
            "cost": cost,
            "costPerQuery": cost_per_query,
            "model": "gpt-4o-mini",
            "trend": {
                "input_change": 0,  # 待实现：对比前一时间段数据
                "output_change": 0,
                "period": "vs previous period",
            },
            "data_available": (input_tokens + output_tokens) > 0,
        }
    except Exception as e:
        logger.error(f"Error fetching token analytics: {e}")
        return {
            "timeRange": time_range,
            "input": 0,
            "output": 0,
            "total": 0,
            "cost": 0,
            "costPerQuery": 0,
            "model": "gpt-4o-mini",
            "trend": {"input_change": 0, "output_change": 0, "period": "vs previous period"},
            "data_available": False,
        }


@router.get("/cache")
async def get_cache_analytics(redis=Depends(get_redis_or_none)):
    """
    Get cache performance analytics.

    Returns:
        - Hit rate
        - Queries saved
        - Latency reduction
    """
    if not redis:
        return {
            "hitRate": 0,
            "saves": 0,
            "latencyReduction": 0,
            "memoryUsage": "0MB",
            "data_available": False,
        }

    try:
        cache_hits = int(await redis.get(f"{STATS_PREFIX}:cache_hits") or 0)
        cache_misses = int(await redis.get(f"{STATS_PREFIX}:cache_misses") or 0)
        total = cache_hits + cache_misses
        hit_rate = round((cache_hits / total * 100), 1) if total > 0 else 0

        # Get memory usage from Redis INFO
        try:
            info = await redis.info("memory")
            memory_bytes = info.get("used_memory", 0)
            memory_mb = round(memory_bytes / (1024 * 1024), 1)
            memory_usage = f"{memory_mb}MB"
        except Exception:
            memory_usage = "0MB"

        return {
            "hitRate": hit_rate,
            "saves": cache_hits,
            "latencyReduction": 0,
            "memoryUsage": memory_usage,
            "data_available": hit_rate > 0,
        }
    except Exception as e:
        logger.error(f"Error fetching cache analytics: {e}")
        return {
            "hitRate": 0,
            "saves": 0,
            "latencyReduction": 0,
            "memoryUsage": "0MB",
            "data_available": False,
        }
