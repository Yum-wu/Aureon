"""Cost Governance API Router"""
from fastapi import APIRouter, Query
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

router = APIRouter(prefix="/api/cost", tags=["Cost Governance"])


# ── Cost Tracking Endpoints ──

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


# ── Budget Management Endpoints ──

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
