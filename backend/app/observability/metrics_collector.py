"""集中式指标采集服务。

从多个数据源（Redis 缓存计数器、RAG pipeline 延迟等）聚合运行时指标，
供 Dashboard WebSocket 和 API 端点消费。

存储策略：
- 原始数据：Redis sorted set，TTL 7 天
- 小时聚合：Redis hash，TTL 30 天
- 日聚合：Redis hash，TTL 90 天
"""

import json
import time
from datetime import datetime, timezone
from typing import Any, Optional

import structlog


logger = structlog.get_logger(__name__)

# ── Redis key 前缀 ──
_METRICS_TS_PREFIX = "metrics:{tenant_id}:ts"
_METRICS_COUNTER_PREFIX = "metrics:{tenant_id}:counters"
_METRICS_HOURLY_PREFIX = "metrics:{tenant_id}:hourly"
_METRICS_DAILY_PREFIX = "metrics:{tenant_id}:daily"

# ── TTL（秒） ──
_TTL_RAW = 7 * 86400       # 7 天
_TTL_HOURLY = 30 * 86400   # 30 天
_TTL_DAILY = 90 * 86400    # 90 天

# ── 最新流水线阶段延迟（模块级，供 WebSocket tick 读取） ──
_latest_pipeline: dict[str, dict[str, float]] = {}  # tenant_id -> {stage: ms}

# ── 单例 ──
_instance: Optional["MetricsCollector"] = None


class MetricsCollector:
    """集中式指标采集器，聚合多源运行时指标。"""

    def __init__(self) -> None:
        self._redis = None

    def _get_redis(self):
        """懒加载 Redis 客户端。"""
        if self._redis is not None:
            return self._redis if self._redis is not False else None
        try:
            from app.cache.redis_client import get_redis
            self._redis = get_redis()
        except Exception as exc:
            logger.warning("metrics_collector_redis_unavailable", error=str(exc))
            self._redis = False
        return self._redis if self._redis and self._redis is not False else None

    async def record_query_metrics(
        self,
        tenant_id: str,
        ttft_ms: float,
        tpot_ms: float,
        tokens_in: int,
        tokens_out: int,
        model: str,
        cache_hit: bool = False,
        error: bool = False,
        pipeline_stages: dict[str, float] | None = None,
    ) -> None:
        """记录单次查询指标，在 RAG 查询完成后调用。

        Args:
            tenant_id: 租户 ID
            ttft_ms: 首 token 延迟（毫秒）
            tpot_ms: 每 token 延迟（毫秒）
            tokens_in: 输入 token 数
            tokens_out: 输出 token 数
            model: 使用的 LLM 模型名
            cache_hit: 是否命中缓存
            error: 是否发生错误
            pipeline_stages: 流水线各阶段延迟 {"retrieval_ms": 85, "rerank_ms": 120, ...}
        """
        r = self._get_redis()
        if r is None:
            return

        now = time.time()
        ts_key = _METRICS_TS_PREFIX.format(tenant_id=tenant_id)
        counter_key = _METRICS_COUNTER_PREFIX.format(tenant_id=tenant_id)

        entry = {
            "ttft_ms": ttft_ms,
            "tpot_ms": tpot_ms,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "model": model,
            "cache_hit": cache_hit,
            "error": error,
            "ts": now,
        }
        if pipeline_stages:
            entry["pipeline"] = pipeline_stages

        try:
            # 写入时间序列 sorted set（score=timestamp）
            pipe = r.pipeline()
            pipe.zadd(ts_key, {json.dumps(entry, ensure_ascii=False): now})
            pipe.expire(ts_key, _TTL_RAW)

            # 更新实时计数器
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            counter_daily = f"{counter_key}:{today}"
            pipe.hincrbyfloat(counter_daily, "total_queries", 1)
            if error:
                pipe.hincrbyfloat(counter_daily, "errors", 1)
            if cache_hit:
                pipe.hincrbyfloat(counter_daily, "cache_hits", 1)
            pipe.hincrbyfloat(counter_daily, "tokens_in", tokens_in)
            pipe.hincrbyfloat(counter_daily, "tokens_out", tokens_out)
            pipe.hincrbyfloat(counter_daily, "ttft_sum", ttft_ms)
            pipe.hincrbyfloat(counter_daily, "tpot_sum", tpot_ms)
            pipe.expire(counter_daily, _TTL_RAW)

            await pipe.execute()
        except Exception as exc:
            logger.warning("metrics_record_failed", tenant_id=tenant_id, error=str(exc))

    async def get_current_metrics(self, tenant_id: str) -> dict[str, Any]:
        """获取最新指标快照。

        Returns:
            包含 qps、ttft_p50/p95、tpot、error_rate、cache_hit_rate、token_usage 的字典
        """
        r = self._get_redis()
        if r is None:
            return _empty_metrics()

        counter_key = _METRICS_COUNTER_PREFIX.format(tenant_id=tenant_id)
        ts_key = _METRICS_TS_PREFIX.format(tenant_id=tenant_id)

        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            counter_daily = f"{counter_key}:{today}"

            # 读取今日计数器
            counters = await r.hgetall(counter_daily)
            total_queries = float(counters.get("total_queries", 0))
            errors = float(counters.get("errors", 0))
            cache_hits = float(counters.get("cache_hits", 0))
            tokens_in = float(counters.get("tokens_in", 0))
            tokens_out = float(counters.get("tokens_out", 0))
            tpot_sum = float(counters.get("tpot_sum", 0))

            # 计算百分位：从最近 5 分钟的原始数据采样
            now = time.time()
            five_min_ago = now - 300
            raw_entries = await r.zrangebyscore(ts_key, five_min_ago, now)
            ttft_list: list[float] = []
            latest_pipeline: dict[str, float] = {}
            for raw in raw_entries:
                try:
                    entry = json.loads(raw)
                    ttft_list.append(entry["ttft_ms"])
                    if "pipeline" in entry:
                        latest_pipeline = entry["pipeline"]
                except (json.JSONDecodeError, KeyError):
                    continue

            ttft_p50, ttft_p95 = _percentiles(ttft_list, 50, 95)

            # 计算 QPS（5 分钟窗口）
            qps = len(ttft_list) / 300.0 if ttft_list else 0.0

            # 计算平均 TPOT
            avg_tpot = (tpot_sum / total_queries) if total_queries > 0 else 0.0

            # 活跃 WebSocket 连接数
            active_connections = await self._get_active_ws_connections()

            return {
                "qps": round(qps, 2),
                "ttft_p50": round(ttft_p50, 1),
                "ttft_p95": round(ttft_p95, 1),
                "tpot": round(avg_tpot, 1),
                "error_rate": round((errors / total_queries * 100) if total_queries > 0 else 0.0, 2),
                "cache_hit_rate": round((cache_hits / total_queries * 100) if total_queries > 0 else 0.0, 2),
                "token_usage": int(tokens_in + tokens_out),
                "active_connections": active_connections,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "pipeline": await self._resolve_pipeline(tenant_id, latest_pipeline),
            }
        except Exception as exc:
            logger.warning("metrics_get_current_failed", tenant_id=tenant_id, error=str(exc))
            return _empty_metrics()

    async def _resolve_pipeline(
        self, tenant_id: str, recent_pipeline: dict[str, float]
    ) -> dict[str, float]:
        """解析 pipeline 数据，优先级：内存缓存 > 近期数据 > Redis 持久化。"""
        # 1. 内存缓存（最快）
        mem = _latest_pipeline.get(tenant_id)
        if mem:
            return mem
        # 2. 近期 5 分钟内的原始数据
        if recent_pipeline:
            return recent_pipeline
        # 3. Redis 持久化（TTL 24h，重启后仍可用）
        try:
            r = self._get_redis()
            if r is not None:
                key = f"aureon:metrics:pipeline:{tenant_id}"
                raw = await r.get(key)
                if raw:
                    return json.loads(raw)
        except Exception:
            pass
        return {}

    async def get_metrics_range(
        self,
        tenant_id: str,
        start_time: float,
        end_time: float,
        interval: str = "5m",
    ) -> list[dict[str, Any]]:
        """获取时间范围内的指标序列，用于图表展示。

        Args:
            tenant_id: 租户 ID
            start_time: 起始时间戳（Unix）
            end_time: 结束时间戳（Unix）
            interval: 聚合间隔（5m/1h/1d）

        Returns:
            按时间排序的指标点列表
        """
        r = self._get_redis()
        if r is None:
            return []

        ts_key = _METRICS_TS_PREFIX.format(tenant_id=tenant_id)

        try:
            raw_entries = await r.zrangebyscore(ts_key, start_time, end_time)
        except Exception as exc:
            logger.warning("metrics_range_query_failed", tenant_id=tenant_id, error=str(exc))
            return []

        # 按间隔分桶聚合
        bucket_seconds = _interval_to_seconds(interval)
        buckets: dict[int, list[dict]] = {}

        for raw in raw_entries:
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            bucket_ts = int(entry.get("ts", 0) // bucket_seconds * bucket_seconds)
            buckets.setdefault(bucket_ts, []).append(entry)

        result: list[dict[str, Any]] = []
        for bucket_ts in sorted(buckets.keys()):
            entries = buckets[bucket_ts]
            ttft_vals = [e["ttft_ms"] for e in entries if "ttft_ms" in e]
            p50, p95 = _percentiles(ttft_vals, 50, 95)
            total = len(entries)
            errors = sum(1 for e in entries if e.get("error"))
            cache_hits = sum(1 for e in entries if e.get("cache_hit"))

            result.append({
                "timestamp": datetime.fromtimestamp(bucket_ts, tz=timezone.utc).isoformat(),
                "qps": round(total / bucket_seconds, 2),
                "ttft_p50": round(p50, 1),
                "ttft_p95": round(p95, 1),
                "tpot": round(
                    sum(e.get("tpot_ms", 0) for e in entries) / total, 1
                ) if total > 0 else 0.0,
                "error_rate": round(errors / total * 100, 2) if total > 0 else 0.0,
                "cache_hit_rate": round(cache_hits / total * 100, 2) if total > 0 else 0.0,
                "query_count": total,
            })

        return result

    async def _get_active_ws_connections(self) -> int:
        """获取当前活跃 WebSocket 连接数。"""
        try:
            from app.api.ws_dashboard import dashboard_manager
            return dashboard_manager.active_count()
        except ImportError:
            return 0


def set_latest_pipeline(tenant_id: str, stages: dict[str, float]) -> None:
    """更新最新流水线阶段延迟（由 RAG 查询流程调用）。

    同时写入内存缓存和 Redis 持久化（TTL 24h），
    确保无查询时 WebSocket 仍能推送上一次的 pipeline 数据。
    """
    _latest_pipeline[tenant_id] = stages
    # 异步持久化到 Redis（fire-and-forget）
    try:
        import asyncio
        from app.dependencies import get_redis_or_none
        r = get_redis_or_none()
        if r is not None:
            key = f"aureon:metrics:pipeline:{tenant_id}"
            asyncio.ensure_future(r.set(key, json.dumps(stages), ex=86400))
    except Exception:
        pass  # 非阻塞，失败不影响主流程


def _empty_metrics() -> dict[str, Any]:
    """返回空指标快照。"""
    return {
        "qps": 0.0,
        "ttft_p50": 0.0,
        "ttft_p95": 0.0,
        "tpot": 0.0,
        "error_rate": 0.0,
        "cache_hit_rate": 0.0,
        "token_usage": 0,
        "active_connections": 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _percentiles(values: list[float], *pcts: int) -> list[float]:
    """计算百分位数。"""
    if not values:
        return [0.0] * len(pcts)
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    result: list[float] = []
    for pct in pcts:
        idx = min(int(n * pct / 100), n - 1)
        result.append(sorted_vals[idx])
    return result


def _interval_to_seconds(interval: str) -> int:
    """将间隔字符串转换为秒数。"""
    mapping = {"5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "1d": 86400}
    return mapping.get(interval, 300)


def get_metrics_collector() -> MetricsCollector:
    """获取全局 MetricsCollector 单例。"""
    global _instance
    if _instance is None:
        _instance = MetricsCollector()
    return _instance
