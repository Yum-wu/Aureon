"""Feature Flags API Router"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.features import (
    FeatureFlagCreate,
    FeatureFlagUpdate,
    FeatureFlagResponse,
    create_flag,
    get_flag_by_name,
    list_flags,
    update_flag,
    delete_flag,
    evaluate_flag,
)

router = APIRouter(prefix="/api/v1/feature-flags", tags=["Feature Flags"])


@router.post("/", response_model=FeatureFlagResponse, status_code=201)
async def create_feature_flag(flag: FeatureFlagCreate):
    """创建新的 Feature Flag"""
    existing = get_flag_by_name(flag.name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Feature flag '{flag.name}' already exists"
        )
    return create_flag(flag)


@router.get("/", response_model=list[FeatureFlagResponse])
async def list_feature_flags(
    status: Optional[str] = Query(None, description="按状态过滤")
):
    """列出所有 Feature Flags"""
    return list_flags(status)


@router.get("/{name}", response_model=FeatureFlagResponse)
async def get_feature_flag(name: str):
    """根据名称获取 Feature Flag"""
    flag = get_flag_by_name(name)
    if not flag:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    return flag


@router.put("/{name}", response_model=FeatureFlagResponse)
async def update_feature_flag(name: str, update: FeatureFlagUpdate):
    """更新 Feature Flag"""
    flag = update_flag(name, update)
    if not flag:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    return flag


@router.delete("/{name}", status_code=204)
async def delete_feature_flag(name: str):
    """删除 Feature Flag"""
    success = delete_flag(name)
    if not success:
        raise HTTPException(status_code=404, detail="Feature flag not found")


@router.get("/evaluate/{name}")
async def evaluate_feature_flag(
    name: str,
    user_id: Optional[str] = Query(None),
    workspace_id: Optional[str] = Query(None),
):
    """评估 Feature Flag 是否启用"""
    enabled = evaluate_flag(name, user_id, workspace_id)
    return {"name": name, "enabled": enabled}
