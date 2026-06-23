"""Cost Governance API Router

包含原有端点（SQLite 存储）和新增聚合端点（Redis 时间序列）。
新增端点需要 ADMIN 角色，且支持租户隔离。
"""

from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.cost import (
    CostRecord,
    BudgetConfig,
    record_cost,
    get_workspace_cost,
    get_user_cost,
    get_top_users,
    create_budget,
    get_budget,
    update_budget,
    get_budget_status,
)
from app.cost.models import BudgetConfigNew, CostSummary
from app.cost.service import get_cost_service
from app.cost.budget_engine import get_budget_engine
from app.security.rbac import UserRole, require_role
from app.multi_tenant.middleware import get_current_tenant_id

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/cost", tags=["Cost Governance"])


# ── 原有端点（SQLite 存储，保持不变） ──

@router.post("/records", status_code=201)
async def create_cost_record(record: CostRecord):
    """记录成本"""
    record_id = record_cost(record)
    return {"id": record_id, "status": "created"}


@router.get("/workspace/{workspace_id}")
async def workspace_cost(
    workspace_id: str,
    days: int = Query(30, ge=1, le=365),
):
    """获取 Workspace 成本统计"""
    return get_workspace_cost(workspace_id, days)


@router.get("/user/{user_id}")
async def user_cost(
    user_id: str,
    days: int = Query(30, ge=1, le=365),
):
    """获取用户成本统计"""
    return get_user_cost(user_id, days)


@router.get("/workspace/{workspace_id}/top-users")
async def workspace_top_users(
    workspace_id: str,
    limit: int = Query(10, ge=1, le=100),
    days: int = Query(30, ge=1, le=365),
):
    """获取高消费用户排行"""
    return {"users": get_top_users(workspace_id, limit, days)}


@router.post("/budgets", response_model=BudgetConfig, status_code=201)
async def create_budget_endpoint(budget: BudgetConfig):
    """创建 Budget 配置"""
    return create_budget(budget)


@router.get("/budgets/{workspace_id}", response_model=BudgetConfig)
async def get_budget_endpoint(workspace_id: str):
    """获取 Budget 配置"""
    budget = get_budget(workspace_id)
    if budget is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Budget not found")
    return budget


@router.put("/budgets/{workspace_id}", response_model=BudgetConfig)
async def update_budget_endpoint(workspace_id: str, update: dict):
    """更新 Budget 配置"""
    budget = update_budget(workspace_id, update)
    if budget is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Budget not found")
    return budget


@router.get("/budgets/{workspace_id}/status")
async def budget_status(workspace_id: str):
    """获取 Budget 状态"""
    return get_budget_status(workspace_id)


# ── 新增聚合端点（Redis 时间序列，需 ADMIN 角色） ──

@router.get("/summary", response_model=CostSummary)
async def cost_summary(
    period: str = Query("30d", pattern=r"^(7d|30d|90d)$", description="聚合周期"),
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """获取成本摘要（需 ADMIN 角色）

    包含总成本、日均消耗、Budget 使用百分比和趋势方向。
    """
    tenant_id = get_current_tenant_id()
    service = get_cost_service()
    return await service.get_summary(tenant_id, period)


@router.get("/trend")
async def cost_trend(
    days: int = Query(30, ge=1, le=365, description="天数"),
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """获取成本趋势数据（需 ADMIN 角色）

    返回按日聚合的成本数据点，用于图表展示。
    """
    tenant_id = get_current_tenant_id()
    service = get_cost_service()
    return await service.get_trend(tenant_id, days)


@router.get("/breakdown")
async def cost_breakdown(
    by: str = Query("model", pattern=r"^(model|workspace)$", description="分组维度"),
    period: str = Query("30d", pattern=r"^(7d|30d|90d)$", description="聚合周期"),
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """获取成本分组明细（需 ADMIN 角色）

    按模型或 Workspace 分组展示成本分布。
    """
    tenant_id = get_current_tenant_id()
    service = get_cost_service()
    agg = await service.get_aggregation(tenant_id, period)
    if by == "workspace":
        return {"breakdown": agg.by_workspace, "period": period}
    return {"breakdown": agg.by_model, "period": period}


@router.get("/top-consumers")
async def cost_top_consumers(
    limit: int = Query(10, ge=1, le=100, description="返回数量"),
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """获取高消费 Workspace 排行（需 ADMIN 角色）

    返回最近 30 天内成本最高的 Workspace 列表。
    """
    tenant_id = get_current_tenant_id()
    service = get_cost_service()
    return await service.get_top_consumers(tenant_id, limit)


@router.get("/budget")
async def get_new_budget(
    workspace_id: Optional[str] = Query(None, description="Workspace ID（空=租户级）"),
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """获取 Budget 配置（需 ADMIN 角色）

    优先返回 Workspace 级配置，其次租户级。
    """
    tenant_id = get_current_tenant_id()
    engine = get_budget_engine()
    config = await engine.get_budget_config(tenant_id, workspace_id)
    if config is None:
        return {"has_budget": False}
    return config.model_dump()


@router.put("/budget")
async def set_new_budget(
    config: BudgetConfigNew,
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """更新 Budget 配置（需 ADMIN 角色）

    设置月度限额、告警阈值和是否硬阻断。
    """
    # 强制使用当前租户 ID
    tenant_id = get_current_tenant_id()
    config.tenant_id = tenant_id
    engine = get_budget_engine()
    await engine.set_budget_config(config)
    return config.model_dump()


@router.get("/export")
async def export_cost(
    start: str = Query(..., description="起始时间 (ISO 格式)"),
    end: str = Query(..., description="结束时间 (ISO 格式)"),
    format: str = Query("csv", pattern=r"^(csv)$", description="导出格式"),
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """导出成本数据（需 ADMIN 角色）

    支持按时间范围导出为 CSV 格式。
    """
    tenant_id = get_current_tenant_id()

    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    except ValueError:
        from app.exceptions import AureonException
        raise AureonException(status_code=400, detail="Invalid date format. Use ISO format (e.g. 2026-01-01T00:00:00)")

    service = get_cost_service()
    csv_data = await service.export_csv(tenant_id, start_dt, end_dt)

    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=cost_export_{tenant_id}.csv",
        },
    )
