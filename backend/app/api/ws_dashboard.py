"""WebSocket Dashboard 端点 — 实时推送系统指标和告警。

端点: /ws/dashboard
认证: 通过 query param ``?token=<API_AUTH_KEY>`` 或 header ``X-API-Key``
消息类型:
  - metrics.tick: 每 5 秒推送一次指标快照
  - alert.fire: 阈值超限时推送告警
"""

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings

logger = structlog.get_logger(__name__)

router = APIRouter()


class DashboardConnectionManager:
    """Dashboard WebSocket 连接管理器。

    管理所有 Dashboard 订阅者的连接、消息广播和断连清理。
    """

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}

    async def connect(self, client_id: str, websocket: WebSocket) -> None:
        """接受新连接并创建消息队列。"""
        await websocket.accept()
        self._connections[client_id] = websocket
        self._queues[client_id] = asyncio.Queue(maxsize=100)
        logger.info("dashboard_ws_connected", client_id=client_id, total=self.active_count())

    async def disconnect(self, client_id: str) -> None:
        """断开连接并清理资源。"""
        self._connections.pop(client_id, None)
        self._queues.pop(client_id, None)
        logger.info("dashboard_ws_disconnected", client_id=client_id, total=self.active_count())

    async def send_to(self, client_id: str, data: dict[str, Any]) -> None:
        """向指定客户端发送 JSON 消息。"""
        ws = self._connections.get(client_id)
        if ws is None:
            return
        try:
            await ws.send_json(data)
        except Exception as exc:
            logger.warning("dashboard_ws_send_failed", client_id=client_id, error=str(exc))
            await self.disconnect(client_id)

    async def broadcast(self, data: dict[str, Any]) -> None:
        """向所有已连接客户端广播消息。"""
        disconnected: list[str] = []
        for client_id, ws in self._connections.items():
            try:
                await ws.send_json(data)
            except Exception:
                disconnected.append(client_id)
        for client_id in disconnected:
            await self.disconnect(client_id)

    def active_count(self) -> int:
        """返回当前活跃连接数。"""
        return len(self._connections)


# 全局单例
dashboard_manager = DashboardConnectionManager()

# ── 告警阈值 ──
_ALERT_THRESHOLDS = {
    "ttft_p95": 2000.0,       # TTFT P95 > 2000ms
    "error_rate": 5.0,        # 错误率 > 5%
    "cache_hit_rate": 50.0,   # 缓存命中率 < 50%
}

# ── 指标采集间隔 ──
_TICK_INTERVAL = 5  # 秒


def _validate_auth(websocket: WebSocket) -> bool:
    """验证 WebSocket 连接的 API Key。

    支持两种方式：
    1. query param ``?token=<API_AUTH_KEY>``
    2. header ``X-API-Key``
    未配置 API_AUTH_KEY 时跳过认证。
    """
    if not settings.api_auth_key:
        return True

    # 优先检查 query param
    token = websocket.query_params.get("token")
    if token and token == settings.api_auth_key:
        return True

    # 其次检查 header
    header_key = websocket.headers.get("x-api-key")
    if header_key and header_key == settings.api_auth_key:
        return True

    return False


def _check_alerts(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """检查指标是否超过告警阈值。"""
    alerts: list[dict[str, Any]] = []

    ttft_p95 = metrics.get("ttft_p95", 0)
    if ttft_p95 > _ALERT_THRESHOLDS["ttft_p95"]:
        alerts.append({
            "type": "ttft_high",
            "message": f"TTFT P95 延迟过高: {ttft_p95:.0f}ms（阈值: {_ALERT_THRESHOLDS['ttft_p95']:.0f}ms）",
            "value": ttft_p95,
            "threshold": _ALERT_THRESHOLDS["ttft_p95"],
        })

    error_rate = metrics.get("error_rate", 0)
    if error_rate > _ALERT_THRESHOLDS["error_rate"]:
        alerts.append({
            "type": "error_rate_high",
            "message": f"错误率过高: {error_rate:.1f}%（阈值: {_ALERT_THRESHOLDS['error_rate']:.0f}%）",
            "value": error_rate,
            "threshold": _ALERT_THRESHOLDS["error_rate"],
        })

    cache_hit_rate = metrics.get("cache_hit_rate", 0)
    if 0 < cache_hit_rate < _ALERT_THRESHOLDS["cache_hit_rate"]:
        alerts.append({
            "type": "cache_hit_low",
            "message": f"缓存命中率过低: {cache_hit_rate:.1f}%（阈值: {_ALERT_THRESHOLDS['cache_hit_rate']:.0f}%）",
            "value": cache_hit_rate,
            "threshold": _ALERT_THRESHOLDS["cache_hit_rate"],
        })

    return alerts


async def _metrics_ticker(client_id: str) -> None:
    """后台任务：每 5 秒采集指标并推送给客户端。"""
    from app.observability.metrics_collector import get_metrics_collector
    from app.multi_tenant.middleware import get_current_tenant_id

    collector = get_metrics_collector()
    tenant_id = get_current_tenant_id()

    while client_id in dashboard_manager._connections:
        try:
            metrics = await collector.get_current_metrics(tenant_id)

            # 推送指标快照
            await dashboard_manager.send_to(client_id, {
                "type": "metrics.tick",
                "data": metrics,
            })

            # 检查告警
            alerts = _check_alerts(metrics)
            for alert in alerts:
                await dashboard_manager.send_to({
                    "type": "alert.fire",
                    "data": {
                        **alert,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                })

            await asyncio.sleep(_TICK_INTERVAL)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("dashboard_ticker_error", client_id=client_id, error=str(exc))
            await asyncio.sleep(_TICK_INTERVAL)


@router.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket) -> None:
    """Dashboard 实时指标 WebSocket 端点。

    认证方式：
    - query param: ``/ws/dashboard?token=<API_AUTH_KEY>``
    - header: ``X-API-Key: <API_AUTH_KEY>``

    推送消息类型：
    - ``metrics.tick``: 每 5 秒推送指标快照（QPS、TTFT、TPOT、错误率等）
    - ``alert.fire``: 阈值超限告警
    """
    # 认证检查
    if not _validate_auth(websocket):
        await websocket.close(code=4001, reason="Unauthorized")
        logger.warning("dashboard_ws_auth_failed")
        return

    # 连接数限制
    from app.config import settings as s
    if dashboard_manager.active_count() >= s.websocket_max_connections:
        await websocket.close(code=1013, reason="Too many connections")
        logger.warning("dashboard_ws_limit_reached")
        return

    client_id = f"dashboard-{id(websocket)}"
    await dashboard_manager.connect(client_id, websocket)

    # 启动指标推送后台任务
    ticker_task = asyncio.create_task(_metrics_ticker(client_id))

    try:
        # 保持连接，等待客户端断开
        while True:
            try:
                data = await websocket.receive_json()
                # 处理心跳
                if data.get("type") == "heartbeat":
                    await dashboard_manager.send_to(client_id, {
                        "type": "heartbeat_ack",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
            except WebSocketDisconnect:
                break
            except Exception as exc:
                logger.warning("dashboard_ws_receive_error", client_id=client_id, error=str(exc))
                break
    finally:
        ticker_task.cancel()
        try:
            await ticker_task
        except asyncio.CancelledError:
            pass
        await dashboard_manager.disconnect(client_id)
