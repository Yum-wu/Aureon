"""Integration Ecosystem API Router"""
from typing import Optional
from fastapi import APIRouter, Query
from app.integration import (
    IntegrationConnector,
    IntegrationSyncLog,
    IMBotConfig,
    create_connector,
    list_connectors,
    get_connector,
    delete_connector,
    update_connector_status,
    create_sync_log,
    complete_sync_log,
    get_sync_logs,
    create_im_bot,
    list_im_bots,
    delete_im_bot,
)

router = APIRouter(prefix="/api/integration", tags=["Integration Ecosystem"])


# ── Integration Connector Endpoints ──

@router.post("/connectors", response_model=IntegrationConnector, status_code=201)
async def create_connector_endpoint(connector: IntegrationConnector):
    """创建集成连接器"""
    return create_connector(connector)


@router.get("/connectors", response_model=list[IntegrationConnector])
async def list_connectors_endpoint():
    """列出所有集成连接器"""
    return list_connectors()


@router.get("/connectors/{name}", response_model=IntegrationConnector)
async def get_connector_endpoint(name: str):
    """获取集成连接器"""
    connector = get_connector(name)
    if connector is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Connector not found")
    return connector


@router.delete("/connectors/{name}", status_code=204)
async def delete_connector_endpoint(name: str):
    """删除集成连接器"""
    success = delete_connector(name)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Connector not found")


@router.put("/connectors/{name}/status")
async def update_connector_status_endpoint(
    name: str,
    status: str,
    error_message: Optional[str] = None,
):
    """更新连接器状态"""
    update_connector_status(name, status, error_message)
    return {"status": "updated"}


# ── Sync Log Endpoints ──

@router.post("/sync-logs", status_code=201)
async def create_sync_log_endpoint(log: IntegrationSyncLog):
    """创建同步日志"""
    log_id = create_sync_log(log)
    return {"id": log_id, "status": "created"}


@router.put("/sync-logs/{log_id}/complete")
async def complete_sync_log_endpoint(
    log_id: int,
    status: str = "success",
    documents_synced: int = 0,
    documents_failed: int = 0,
):
    """完成同步日志"""
    complete_sync_log(log_id, status, documents_synced, documents_failed)
    return {"status": "updated"}


@router.get("/sync-logs")
async def list_sync_logs(
    connector_id: Optional[int] = None,
    limit: int = Query(10, ge=1, le=100),
):
    """获取同步日志"""
    return {"logs": get_sync_logs(connector_id, limit)}


# ── IM Bot Endpoints ──

@router.post("/im-bots", response_model=IMBotConfig, status_code=201)
async def create_im_bot_endpoint(bot: IMBotConfig):
    """创建 IM Bot 配置"""
    return create_im_bot(bot)


@router.get("/im-bots", response_model=list[IMBotConfig])
async def list_im_bots_endpoint(workspace_id: Optional[str] = None):
    """列出 IM Bot 配置"""
    return list_im_bots(workspace_id)


@router.delete("/im-bots/{platform}/{workspace_id}", status_code=204)
async def delete_im_bot_endpoint(platform: str, workspace_id: str):
    """删除 IM Bot 配置"""
    success = delete_im_bot(platform, workspace_id)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="IM Bot not found")
