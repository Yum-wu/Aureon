# -*- coding: utf-8 -*-
"""Audit log API routes.

GET /api/audit/logs  - Query audit logs with filtering and pagination
GET /api/audit/stats - Aggregated audit statistics
"""

from fastapi import APIRouter, Query
import structlog

from app.audit.models import AuditLogsResponse, AuditStatsResponse
from app.audit.service import get_audit_logs, get_audit_stats

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["audit"])


@router.get("/logs", response_model=AuditLogsResponse)
async def list_audit_logs(
    tenant_id: str = Query("default", description="Tenant ID for filtering"),
    limit: int = Query(50, ge=1, le=500, description="Max logs to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """Query audit logs for a tenant.

    Returns a paginated list of audit log entries, ordered by most recent first.
    Only read operations - the audit_logs table is append-only.
    """
    return await get_audit_logs(tenant_id=tenant_id, limit=limit, offset=offset)


@router.get("/stats", response_model=AuditStatsResponse)
async def audit_stats(
    tenant_id: str = Query("default", description="Tenant ID for filtering"),
):
    """Aggregate audit statistics for a tenant.

    Includes total count, action breakdown, resource type breakdown,
    and recent activity counts (1h, 24h).
    """
    return await get_audit_stats(tenant_id=tenant_id)
