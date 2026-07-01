"""Cost Governance API — 成本查询端点"""

import structlog
from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse

from app.cost.service import CostSummary, get_cost_service
from app.multi_tenant.middleware import get_current_tenant_id
from app.security.rbac import UserRole, require_role

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/cost", tags=["cost"])


def _get_time_range_days(period: str) -> int:
    return {"7d": 7, "30d": 30, "90d": 90}.get(period, 30)


@router.get("/summary")
async def get_summary(period: str = Query("30d"), _=Depends(require_role(UserRole.ADMIN))):
    tenant_id = get_current_tenant_id()
    svc = get_cost_service()
    summary: CostSummary = await svc.get_summary(tenant_id, period)
    return summary.model_dump()


@router.get("/trend")
async def get_trend(days: int = Query(30, ge=1, le=365), _=Depends(require_role(UserRole.ADMIN))):
    tenant_id = get_current_tenant_id()
    svc = get_cost_service()
    return await svc.get_trend(tenant_id, days)


@router.get("/breakdown")
async def get_breakdown(by: str = Query("model"), period: str = Query("30d"), _=Depends(require_role(UserRole.ADMIN))):
    tenant_id = get_current_tenant_id()
    svc = get_cost_service()
    agg = await svc.get_aggregation(tenant_id, period)
    if by == "model":
        return {"breakdown": agg.by_model}
    return {"breakdown": agg.by_workspace}


@router.get("/top-consumers")
async def get_top_consumers(limit: int = Query(10, ge=1, le=100), _=Depends(require_role(UserRole.ADMIN))):
    tenant_id = get_current_tenant_id()
    svc = get_cost_service()
    return await svc.get_top_consumers(tenant_id, limit)


@router.get("/export", response_class=PlainTextResponse)
async def export_csv(
    start: str = Query(..., description="ISO 8601 start date"),
    end: str = Query(..., description="ISO 8601 end date"),
    _=Depends(require_role(UserRole.ADMIN)),
):
    from datetime import datetime
    tenant_id = get_current_tenant_id()
    svc = get_cost_service()
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    return PlainTextResponse(await svc.export_csv(tenant_id, start_dt, end_dt), media_type="text/csv")
