"""Knowledge Intelligence API Router"""
from typing import Optional
from fastapi import APIRouter, Query
from app.knowledge import (
    DocumentVersion,
    ExportRequest,
    ExportRecord,
    create_document_version,
    get_document_versions,
    get_latest_version,
    create_export_record,
    complete_export,
    get_export_records,
)

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge Intelligence"])


# ── Document Version Control Endpoints ──

@router.post("/versions", status_code=201)
async def create_version(version: DocumentVersion):
    """创建文档版本"""
    version_id = create_document_version(version)
    return {"id": version_id, "status": "created"}


@router.get("/versions/{document_id}")
async def list_versions(
    document_id: str,
    limit: int = Query(10, ge=1, le=100),
):
    """获取文档版本历史"""
    return {"versions": get_document_versions(document_id, limit)}


@router.get("/versions/{document_id}/latest")
async def latest_version(document_id: str):
    """获取最新版本"""
    version = get_latest_version(document_id)
    if version is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No versions found")
    return version


# ── Export Endpoints ──

@router.post("/exports", status_code=201)
async def create_export(record: ExportRecord):
    """创建导出记录"""
    record_id = create_export_record(record)
    return {"id": record_id, "status": "created"}


@router.put("/exports/{record_id}/complete")
async def complete_export_endpoint(
    record_id: int,
    status: str = "completed",
    file_path: Optional[str] = None,
    file_size: int = 0,
):
    """完成导出"""
    complete_export(record_id, status, file_path, file_size)
    return {"status": "updated"}


@router.get("/exports")
async def list_exports(limit: int = Query(10, ge=1, le=100)):
    """获取导出记录"""
    return {"exports": get_export_records(limit)}
