"""Reliability API Router"""
from typing import Optional
from fastapi import APIRouter, Query
from app.reliability import (
    BackupRecord,
    IncidentRecord,
    SLOConfig,
    create_backup_record,
    complete_backup,
    get_recent_backups,
    create_incident,
    resolve_incident,
    get_open_incidents,
    create_slo_config,
    get_slo_configs,
    get_slo_status,
)

router = APIRouter(prefix="/api/reliability", tags=["Reliability"])


# ── Backup Endpoints ──

@router.post("/backups", status_code=201)
async def create_backup(record: BackupRecord):
    """创建备份记录"""
    record_id = create_backup_record(record)
    return {"id": record_id, "status": "created"}


@router.put("/backups/{record_id}/complete")
async def complete_backup_endpoint(
    record_id: int,
    status: str = "completed",
    file_path: Optional[str] = None,
):
    """完成备份"""
    complete_backup(record_id, status, file_path)
    return {"status": "updated"}


@router.get("/backups")
async def list_backups(limit: int = Query(10, ge=1, le=100)):
    """获取最近的备份记录"""
    return {"backups": get_recent_backups(limit)}


# ── Incident Endpoints ──

@router.post("/incidents", status_code=201)
async def create_incident_endpoint(record: IncidentRecord):
    """创建事件记录"""
    record_id = create_incident(record)
    return {"id": record_id, "status": "created"}


@router.put("/incidents/{incident_id}/resolve")
async def resolve_incident_endpoint(incident_id: str, resolution: str):
    """解决事件"""
    resolve_incident(incident_id, resolution)
    return {"status": "resolved"}


@router.get("/incidents/open")
async def list_open_incidents():
    """获取未解决的事件"""
    return {"incidents": get_open_incidents()}


# ── SLO Endpoints ──

@router.post("/slo", response_model=SLOConfig, status_code=201)
async def create_slo_endpoint(config: SLOConfig):
    """创建 SLO 配置"""
    return create_slo_config(config)


@router.get("/slo", response_model=list[SLOConfig])
async def list_slo_configs():
    """获取所有 SLO 配置"""
    return get_slo_configs()


@router.get("/slo/status")
async def slo_status():
    """获取 SLO 状态"""
    return {"slos": get_slo_status()}
