"""Observability API Router"""
from typing import Optional
from fastapi import APIRouter, Query
from app.observability import (
    get_recent_traces,
    get_trace_stats,
)

router = APIRouter(prefix="/api/observability", tags=["Observability"])


@router.get("/traces")
async def list_traces(limit: int = Query(100, ge=1, le=1000)):
    """获取最近的查询追踪"""
    traces = get_recent_traces(limit)
    return {"traces": traces, "count": len(traces)}


@router.get("/stats")
async def observability_stats():
    """获取可观测性统计数据"""
    return get_trace_stats()
