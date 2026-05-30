"""Evaluation Dashboard API Router"""
from typing import Optional
from fastapi import APIRouter, Query
from app.evaluation import (
    EvaluationMetric,
    BenchmarkRun,
    save_evaluation_metric,
    get_latest_metrics,
    save_benchmark_run,
    get_benchmark_runs,
    get_evaluation_summary,
)

router = APIRouter(prefix="/api/evaluation", tags=["Evaluation"])


@router.post("/metrics", status_code=201)
async def create_evaluation_metric(metric: EvaluationMetric):
    """创建评估指标"""
    metric_id = save_evaluation_metric(metric)
    return {"id": metric_id, "status": "created"}


@router.get("/metrics")
async def list_evaluation_metrics(
    metric_type: Optional[str] = Query(None, description="按类型过滤"),
):
    """列出评估指标"""
    metrics = get_latest_metrics(metric_type)
    return {"metrics": metrics, "count": len(metrics)}


@router.get("/summary")
async def evaluation_summary():
    """获取评估摘要"""
    return get_evaluation_summary()


@router.post("/benchmarks", status_code=201)
async def create_benchmark_run(run: BenchmarkRun):
    """创建基准测试运行"""
    run_id = save_benchmark_run(run)
    return {"id": run_id, "status": "created"}


@router.get("/benchmarks")
async def list_benchmark_runs(
    benchmark_set: Optional[str] = Query(None, description="按基准测试集过滤"),
    limit: int = Query(10, ge=1, le=100),
):
    """列出基准测试运行"""
    runs = get_benchmark_runs(benchmark_set, limit)
    return {"runs": runs, "count": len(runs)}
