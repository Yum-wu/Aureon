"""Budget 阈值检查与告警引擎。

在每次 cost.record_usage() 后调用，检查是否超过配置的阈值，
并触发 WebSocket 告警通知。
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog

from app.cost.models import BudgetConfigNew, BudgetAlert

logger = structlog.get_logger(__name__)

# ── Redis key 模板 ──
_BUDGET_CONFIG_KEY = "budget:{tenant_id}:config"
_BUDGET_CONFIG_WS_KEY = "budget:{tenant_id}:ws:{workspace_id}:config"

# ── 单例 ──
_instance: Optional["BudgetEngine"] = None


class BudgetEngine:
    """Budget 阈值检查与告警引擎。"""

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
            logger.warning("budget_engine_redis_unavailable", error=str(exc))
            self._redis = False
        return self._redis if self._redis and self._redis is not False else None

    async def check_budget(
        self, tenant_id: str, workspace_id: Optional[str] = None
    ) -> Optional[BudgetAlert]:
        """检查 Budget 是否超限。

        优先检查 Workspace 级 Budget，其次检查租户级。

        Args:
            tenant_id: 租户 ID
            workspace_id: Workspace ID（可选）

        Returns:
            BudgetAlert 实例（超限时），或 None
        """
        config = await self.get_budget_config(tenant_id, workspace_id)
        if config is None:
            return None

        # 获取当前月度用量
        current_usage = await self._get_monthly_usage(tenant_id, workspace_id)
        if config.monthly_limit_usd <= 0:
            return None

        percentage = current_usage / config.monthly_limit_usd

        # 判断阈值类型
        threshold_type: Optional[str] = None
        if config.hard_limit and percentage >= 1.0:
            threshold_type = "hard_limit"
        elif percentage >= config.critical_threshold:
            threshold_type = "critical"
        elif percentage >= config.warning_threshold:
            threshold_type = "warning"

        if threshold_type is None:
            return None

        alert = BudgetAlert(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            threshold_type=threshold_type,
            current_usage=round(current_usage, 4),
            budget_limit=config.monthly_limit_usd,
            percentage=round(percentage * 100, 2),
            created_at=datetime.now(timezone.utc),
        )

        # 通过 WebSocket 广播告警
        await self._fire_alert(alert)

        return alert

    async def get_budget_config(
        self, tenant_id: str, workspace_id: Optional[str] = None
    ) -> Optional[BudgetConfigNew]:
        """获取 Budget 配置。

        优先返回 Workspace 级配置，其次租户级。

        Args:
            tenant_id: 租户 ID
            workspace_id: Workspace ID（可选）

        Returns:
            BudgetConfigNew 实例，或 None
        """
        r = self._get_redis()
        if r is None:
            return None

        # 优先查 Workspace 级
        if workspace_id:
            ws_key = _BUDGET_CONFIG_WS_KEY.format(tenant_id=tenant_id, workspace_id=workspace_id)
            try:
                raw = await r.get(ws_key)
                if raw:
                    return BudgetConfigNew.model_validate_json(raw)
            except Exception as exc:
                logger.warning("budget_config_ws_read_failed", error=str(exc))

        # 其次查租户级
        tenant_key = _BUDGET_CONFIG_KEY.format(tenant_id=tenant_id)
        try:
            raw = await r.get(tenant_key)
            if raw:
                return BudgetConfigNew.model_validate_json(raw)
        except Exception as exc:
            logger.warning("budget_config_tenant_read_failed", error=str(exc))

        return None

    async def set_budget_config(self, config: BudgetConfigNew) -> None:
        """保存 Budget 配置。

        Args:
            config: BudgetConfigNew 实例
        """
        r = self._get_redis()
        if r is None:
            return

        serialized = config.model_dump_json()
        try:
            if config.workspace_id:
                key = _BUDGET_CONFIG_WS_KEY.format(
                    tenant_id=config.tenant_id,
                    workspace_id=config.workspace_id,
                )
            else:
                key = _BUDGET_CONFIG_KEY.format(tenant_id=config.tenant_id)

            await r.set(key, serialized)
            logger.info(
                "budget_config_saved",
                tenant_id=config.tenant_id,
                workspace_id=config.workspace_id,
            )
        except Exception as exc:
            logger.warning("budget_config_save_failed", error=str(exc))

    async def should_block_query(self, tenant_id: str) -> bool:
        """检查是否应阻断查询（hard limit 超限）。

        Args:
            tenant_id: 租户 ID

        Returns:
            True 表示应阻断
        """
        config = await self.get_budget_config(tenant_id)
        if config is None or not config.hard_limit:
            return False

        current_usage = await self._get_monthly_usage(tenant_id)
        return current_usage >= config.monthly_limit_usd

    async def _get_monthly_usage(
        self, tenant_id: str, workspace_id: Optional[str] = None
    ) -> float:
        """获取本月累计用量。

        从 Redis 日聚合数据中汇总。
        """
        r = self._get_redis()
        if r is None:
            return 0.0

        total = 0.0
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        days_in_month = (now - month_start).days + 1

        try:
            for i in range(days_in_month):
                day = (month_start + __import__("datetime").timedelta(days=i)).strftime("%Y-%m-%d")
                daily_key = f"cost:{tenant_id}:daily:{day}"
                daily_data = await r.hgetall(daily_key)
                if daily_data:
                    if workspace_id:
                        ws_field = f"ws:{workspace_id}"
                        total += float(daily_data.get(ws_field, 0))
                    else:
                        total += float(daily_data.get("total_cost", 0))
        except Exception as exc:
            logger.warning("budget_monthly_usage_failed", tenant_id=tenant_id, error=str(exc))

        return total

    async def _fire_alert(self, alert: BudgetAlert) -> None:
        """通过 WebSocket 广播 Budget 告警。"""
        try:
            from app.api.ws_dashboard import dashboard_manager
            await dashboard_manager.broadcast({
                "type": "alert.fire",
                "data": {
                    "alert_type": "budget",
                    "threshold_type": alert.threshold_type,
                    "tenant_id": alert.tenant_id,
                    "workspace_id": alert.workspace_id,
                    "current_usage": alert.current_usage,
                    "budget_limit": alert.budget_limit,
                    "percentage": alert.percentage,
                    "message": (
                        f"Budget {alert.threshold_type}: "
                        f"${alert.current_usage:.2f} / ${alert.budget_limit:.2f} "
                        f"({alert.percentage:.1f}%)"
                    ),
                    "timestamp": alert.created_at.isoformat(),
                },
            })
        except Exception as exc:
            logger.warning("budget_alert_broadcast_failed", error=str(exc))


def get_budget_engine() -> BudgetEngine:
    """获取全局 BudgetEngine 单例。"""
    global _instance
    if _instance is None:
        _instance = BudgetEngine()
    return _instance
