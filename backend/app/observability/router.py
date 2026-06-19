"""Observability API Router"""
from fastapi import APIRouter, Query
from app.observability import (
    get_recent_traces,
    get_trace_stats,
)

router = APIRouter(tags=["Observability"])


@router.get("/traces")
async def list_traces(limit: int = Query(100, ge=1, le=1000)):
    """获取最近的查询追踪"""
    traces = get_recent_traces(limit)
    return {"traces": traces, "count": len(traces)}


@router.get("/stats")
async def observability_stats():
    """获取可观测性统计数据"""
    return get_trace_stats()


@router.get("/prompts")
async def list_prompts():
    """获取所有缓存的提示词（用于调试/管理）"""
    from app.observability.prompt_manager import get_all_prompts

    prompts = get_all_prompts()
    return {
        name: value[:100] + "..." if len(value) > 100 else value
        for name, value in prompts.items()
    }


@router.post("/prompts/refresh")
async def refresh_prompts_endpoint():
    """手动从 LangFuse 刷新所有提示词"""
    from app.observability.prompt_manager import refresh_prompts

    count = await refresh_prompts()
    return {"refreshed": count}
