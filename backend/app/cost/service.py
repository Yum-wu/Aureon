"""Cost 聚合与查询服务。

基于 Redis sorted set 实现时间序列存储，支持按时间范围查询、
按模型/Workspace 分组聚合、趋势分析和 CSV 导出。
"""

import csv
import json
import time
from datetime import datetime, timezone, timedelta
from io import StringIO
from typing import Any, Optional

import structlog

from app.cost.models import TokenUsage, CostAggregation, CostSummary

logger = structlog.get_logger(__name__)

# ── Redis key 模板 ──
_COST_TS_KEY = "cost:{tenant_id}:ts"
_COST_DAILY_KEY = "cost:{tenant_id}:daily:{date}"

# ── TTL ──
_TTL_RAW = 90 * 86400   # 90 天
_TTL_DAILY = 90 * 86400  # 90 天

# ── 单例 ──
_instance: Optional["CostService"] = None


class CostService:
    """成本聚合与查询服务。"""

    def _get_redis(self):
        """获取 Redis 客户端（每次调用都检查，支持冷启动后重连）。

        直接使用 redis_client 的单例，它内置了失败重试机制。
        不缓存结果，避免冷启动时缓存 False 后永不重连。
        """
        try:
            from app.cache.redis_client import get_redis
            client = get_redis()
            if client is None or client is False:
                return None
            return client
        except Exception as exc:
            logger.warning("cost_service_redis_unavailable", error=str(exc))
            return None

    async def record_usage(self, usage: TokenUsage) -> None:
        """记录一次 Token 使用（直接 Redis 命令，避免 pipeline 挂起）。

        Args:
            usage: TokenUsage 实例
        """
        r = self._get_redis()
        if r is None:
            logger.warning("cost_record_no_redis", tenant_id=usage.tenant_id)
            return

        now = time.time()
        ts_key = _COST_TS_KEY.format(tenant_id=usage.tenant_id)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_key = _COST_DAILY_KEY.format(tenant_id=usage.tenant_id, date=today)

        entry = json.dumps({
            "model": usage.model,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cost_usd": usage.cost_usd,
            "workspace_id": usage.workspace_id or "",
            "user_id": usage.user_id or "",
            "ts": now,
        }, ensure_ascii=False)

        try:
            # 直接写入（不用 pipeline，避免连接池阻塞）
            await r.zadd(ts_key, {entry: now})
            await r.expire(ts_key, _TTL_RAW)
            await r.hincrbyfloat(daily_key, "total_cost", usage.cost_usd)
            await r.hincrbyfloat(daily_key, "total_input_tokens", usage.input_tokens)
            await r.hincrbyfloat(daily_key, "total_output_tokens", usage.output_tokens)
            await r.hincrbyfloat(daily_key, "query_count", 1)
            model_field = f"model:{usage.model}"
            await r.hincrbyfloat(daily_key, model_field, usage.cost_usd)
            if usage.workspace_id:
                ws_field = f"ws:{usage.workspace_id}"
                await r.hincrbyfloat(daily_key, ws_field, usage.cost_usd)
            await r.expire(daily_key, _TTL_DAILY)
            logger.info("cost_record_success", tenant_id=usage.tenant_id, cost_usd=usage.cost_usd, daily_key=daily_key)
        except Exception as exc:
            logger.warning("cost_record_failed", tenant_id=usage.tenant_id, error=str(exc))

    async def get_aggregation(self, tenant_id: str, period: str) -> CostAggregation:
        """获取成本聚合数据。

        Args:
            tenant_id: 租户 ID
            period: 聚合周期（7d/30d/90d）

        Returns:
            CostAggregation 实例
        """
        r = self._get_redis()
        if r is None:
            return CostAggregation(tenant_id=tenant_id, period=period)

        days = _period_to_days(period)
        since = datetime.now(timezone.utc) - timedelta(days=days)

        total_cost = 0.0
        total_input_tokens = 0
        total_output_tokens = 0
        by_model: dict[str, float] = {}
        by_workspace: dict[str, float] = {}
        trend: list[dict[str, Any]] = []

        try:
            # 读取每日聚合
            for i in range(days):
                day = (since + timedelta(days=i)).strftime("%Y-%m-%d")
                daily_key = _COST_DAILY_KEY.format(tenant_id=tenant_id, date=day)
                daily_data = await r.hgetall(daily_key)
                if not daily_data:
                    trend.append({"date": day, "cost": 0.0, "tokens": 0})
                    continue

                day_cost = float(daily_data.get("total_cost", 0))
                day_input = int(float(daily_data.get("total_input_tokens", 0)))
                day_output = int(float(daily_data.get("total_output_tokens", 0)))

                total_cost += day_cost
                total_input_tokens += day_input
                total_output_tokens += day_output

                # 按模型聚合
                for k, v in daily_data.items():
                    if k.startswith("model:"):
                        model_name = k[6:]
                        by_model[model_name] = by_model.get(model_name, 0) + float(v)
                    elif k.startswith("ws:"):
                        ws_id = k[3:]
                        by_workspace[ws_id] = by_workspace.get(ws_id, 0) + float(v)

                trend.append({
                    "date": day,
                    "cost": round(day_cost, 4),
                    "tokens": day_input + day_output,
                })
        except Exception as exc:
            logger.warning("cost_aggregation_failed", tenant_id=tenant_id, error=str(exc))

        burn_rate = total_cost / days if days > 0 else 0.0

        return CostAggregation(
            tenant_id=tenant_id,
            period=period,
            total_cost=round(total_cost, 4),
            burn_rate=round(burn_rate, 4),
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            by_model={k: round(v, 4) for k, v in by_model.items()},
            by_workspace={k: round(v, 4) for k, v in by_workspace.items()},
            trend=trend,
        )

    async def get_trend(self, tenant_id: str, days: int = 30) -> list[dict[str, Any]]:
        """获取成本趋势数据。

        Args:
            tenant_id: 租户 ID
            days: 天数

        Returns:
            日趋势数据点列表
        """
        r = self._get_redis()
        if r is None:
            return []

        result: list[dict[str, Any]] = []
        try:
            for i in range(days):
                day_dt = datetime.now(timezone.utc) - timedelta(days=days - 1 - i)
                day = day_dt.strftime("%Y-%m-%d")
                daily_key = _COST_DAILY_KEY.format(tenant_id=tenant_id, date=day)
                daily_data = await r.hgetall(daily_key)
                day_cost = float(daily_data.get("total_cost", 0)) if daily_data else 0.0
                result.append({"date": day, "cost": round(day_cost, 4)})
        except Exception as exc:
            logger.warning("cost_trend_failed", tenant_id=tenant_id, error=str(exc))

        return result

    async def get_top_consumers(
        self, tenant_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """获取高消费排行。

        Args:
            tenant_id: 租户 ID
            limit: 返回数量上限

        Returns:
            按 workspace 或用户排序的消费列表
        """
        r = self._get_redis()
        if r is None:
            return []

        # 从最近 30 天的日聚合中提取
        consumers: dict[str, float] = {}
        try:
            for i in range(30):
                day = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
                daily_key = _COST_DAILY_KEY.format(tenant_id=tenant_id, date=day)
                daily_data = await r.hgetall(daily_key)
                if not daily_data:
                    continue
                for k, v in daily_data.items():
                    if k.startswith("ws:"):
                        ws_id = k[3:]
                        consumers[ws_id] = consumers.get(ws_id, 0) + float(v)
        except Exception as exc:
            logger.warning("cost_top_consumers_failed", tenant_id=tenant_id, error=str(exc))

        sorted_consumers = sorted(consumers.items(), key=lambda x: x[1], reverse=True)[:limit]
        return [
            {"workspace_id": ws_id, "cost_usd": round(cost, 4)}
            for ws_id, cost in sorted_consumers
        ]

    async def get_summary(self, tenant_id: str, period: str = "30d") -> CostSummary:
        """获取成本摘要（Dashboard 用）。

        Args:
            tenant_id: 租户 ID
            period: 聚合周期

        Returns:
            CostSummary 实例
        """
        agg = await self.get_aggregation(tenant_id, period)

        # 计算 Budget 使用百分比
        budget_used_pct = 0.0
        budget_total = None
        try:
            from app.cost.budget_engine import get_budget_engine
            engine = get_budget_engine()
            config = await engine.get_budget_config(tenant_id)
            if config is not None:
                budget_total = config.monthly_limit_usd
                budget_used_pct = (agg.total_cost / config.monthly_limit_usd * 100) if config.monthly_limit_usd > 0 else 0.0
        except Exception:
            pass

        # 判断趋势方向
        trend_direction = "stable"
        if len(agg.trend) >= 7:
            recent = sum(d.get("cost", 0) for d in agg.trend[-3:])
            earlier = sum(d.get("cost", 0) for d in agg.trend[-7:-4])
            if earlier > 0:
                ratio = recent / earlier
                if ratio > 1.1:
                    trend_direction = "up"
                elif ratio < 0.9:
                    trend_direction = "down"

        total_tokens = agg.total_input_tokens + agg.total_output_tokens
        return CostSummary(
            total_cost=agg.total_cost,
            burn_rate=agg.burn_rate,
            total_tokens=total_tokens,
            budget_used_pct=round(budget_used_pct, 2),
            budget_total=budget_total,
            trend_direction=trend_direction,
            data_available=agg.total_cost > 0 or total_tokens > 0,
        )

    async def export_csv(
        self, tenant_id: str, start: datetime, end: datetime
    ) -> str:
        """导出成本数据为 CSV。

        Args:
            tenant_id: 租户 ID
            start: 起始时间
            end: 结束时间

        Returns:
            CSV 字符串
        """
        r = self._get_redis()
        if r is None:
            return ""

        ts_key = _COST_TS_KEY.format(tenant_id=tenant_id)
        start_ts = start.timestamp()
        end_ts = end.timestamp()

        try:
            raw_entries = await r.zrangebyscore(ts_key, start_ts, end_ts)
        except Exception as exc:
            logger.warning("cost_export_csv_failed", tenant_id=tenant_id, error=str(exc))
            return ""

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["timestamp", "model", "input_tokens", "output_tokens", "cost_usd", "workspace_id", "user_id"])

        for raw in raw_entries:
            try:
                entry = json.loads(raw)
                ts = datetime.fromtimestamp(entry.get("ts", 0), tz=timezone.utc).isoformat()
                writer.writerow([
                    ts,
                    entry.get("model", ""),
                    entry.get("input_tokens", 0),
                    entry.get("output_tokens", 0),
                    entry.get("cost_usd", 0),
                    entry.get("workspace_id", ""),
                    entry.get("user_id", ""),
                ])
            except (json.JSONDecodeError, KeyError):
                continue

        return output.getvalue()


def _period_to_days(period: str) -> int:
    """将周期字符串转换为天数。"""
    mapping = {"7d": 7, "30d": 30, "90d": 90}
    return mapping.get(period, 30)


def get_cost_service() -> CostService:
    """获取全局 CostService 单例。"""
    global _instance
    if _instance is None:
        _instance = CostService()
    return _instance
