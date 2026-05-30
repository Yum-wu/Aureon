"""Evaluation Dashboard - RAG 质量评估展示"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()


class EvaluationMetric(BaseModel):
    """评估指标"""
    id: Optional[int] = None
    metric_name: str = Field(..., description="指标名称")
    metric_value: float = Field(..., description="指标值")
    metric_type: str = Field(..., description="recall/faithfulness/hallucination")
    benchmark_set: Optional[str] = None
    model_version: Optional[str] = None
    created_at: Optional[str] = None


class BenchmarkRun(BaseModel):
    """基准测试运行"""
    id: Optional[int] = None
    run_id: str = Field(..., description="运行 ID")
    benchmark_set: str = Field(..., description="基准测试集名称")
    total_queries: int = 0
    successful_queries: int = 0
    failed_queries: int = 0
    avg_latency_ms: float = 0.0
    recall_at_1: float = 0.0
    recall_at_3: float = 0.0
    recall_at_5: float = 0.0
    faithfulness_score: float = 0.0
    hallucination_rate: float = 0.0
    mrr: float = 0.0
    ndcg: float = 0.0
    status: str = "pending"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


def init_evaluation_tables():
    """初始化评估表"""
    from app.memory.db import get_db

    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS evaluation_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            metric_type TEXT NOT NULL,
            benchmark_set TEXT,
            model_version TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS benchmark_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT UNIQUE NOT NULL,
            benchmark_set TEXT NOT NULL,
            total_queries INTEGER DEFAULT 0,
            successful_queries INTEGER DEFAULT 0,
            failed_queries INTEGER DEFAULT 0,
            avg_latency_ms REAL DEFAULT 0,
            recall_at_1 REAL DEFAULT 0,
            recall_at_3 REAL DEFAULT 0,
            recall_at_5 REAL DEFAULT 0,
            faithfulness_score REAL DEFAULT 0,
            hallucination_rate REAL DEFAULT 0,
            mrr REAL DEFAULT 0,
            ndcg REAL DEFAULT 0,
            status TEXT DEFAULT 'pending',
            started_at TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_evaluation_metrics_type ON evaluation_metrics(metric_type)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_benchmark_runs_set ON benchmark_runs(benchmark_set)
    """)
    conn.commit()


def save_evaluation_metric(metric: EvaluationMetric) -> int:
    """保存评估指标"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    cursor = conn.execute(
        """
        INSERT INTO evaluation_metrics (metric_name, metric_value, metric_type, benchmark_set, model_version, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            metric.metric_name,
            metric.metric_value,
            metric.metric_type,
            metric.benchmark_set,
            metric.model_version,
            now,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_latest_metrics(metric_type: Optional[str] = None) -> list[EvaluationMetric]:
    """获取最新的评估指标"""
    from app.memory.db import get_db

    conn = get_db()
    if metric_type:
        rows = conn.execute(
            """
            SELECT * FROM evaluation_metrics
            WHERE metric_type = ?
            ORDER BY created_at DESC
            LIMIT 10
            """,
            (metric_type,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM evaluation_metrics ORDER BY created_at DESC LIMIT 50"
        ).fetchall()

    return [
        EvaluationMetric(
            id=row["id"],
            metric_name=row["metric_name"],
            metric_value=row["metric_value"],
            metric_type=row["metric_type"],
            benchmark_set=row["benchmark_set"],
            model_version=row["model_version"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def save_benchmark_run(run: BenchmarkRun) -> int:
    """保存基准测试运行"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    cursor = conn.execute(
        """
        INSERT INTO benchmark_runs (
            run_id, benchmark_set, total_queries, successful_queries, failed_queries,
            avg_latency_ms, recall_at_1, recall_at_3, recall_at_5,
            faithfulness_score, hallucination_rate, mrr, ndcg,
            status, started_at, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run.run_id,
            run.benchmark_set,
            run.total_queries,
            run.successful_queries,
            run.failed_queries,
            run.avg_latency_ms,
            run.recall_at_1,
            run.recall_at_3,
            run.recall_at_5,
            run.faithfulness_score,
            run.hallucination_rate,
            run.mrr,
            run.ndcg,
            run.status,
            run.started_at or now,
            run.completed_at,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_benchmark_runs(
    benchmark_set: Optional[str] = None,
    limit: int = 10,
) -> list[BenchmarkRun]:
    """获取基准测试运行"""
    from app.memory.db import get_db

    conn = get_db()
    if benchmark_set:
        rows = conn.execute(
            """
            SELECT * FROM benchmark_runs
            WHERE benchmark_set = ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (benchmark_set, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM benchmark_runs
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        BenchmarkRun(
            id=row["id"],
            run_id=row["run_id"],
            benchmark_set=row["benchmark_set"],
            total_queries=row["total_queries"],
            successful_queries=row["successful_queries"],
            failed_queries=row["failed_queries"],
            avg_latency_ms=row["avg_latency_ms"],
            recall_at_1=row["recall_at_1"],
            recall_at_3=row["recall_at_3"],
            recall_at_5=row["recall_at_5"],
            faithfulness_score=row["faithfulness_score"],
            hallucination_rate=row["hallucination_rate"],
            mrr=row["mrr"],
            ndcg=row["ndcg"],
            status=row["status"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )
        for row in rows
    ]


def get_evaluation_summary() -> dict:
    """获取评估摘要"""
    from app.memory.db import get_db

    conn = get_db()

    # 最新的 Recall@3
    latest_recall = conn.execute(
        """
        SELECT metric_value FROM evaluation_metrics
        WHERE metric_name = 'recall_at_3'
        ORDER BY created_at DESC LIMIT 1
        """
    ).fetchone()
    latest_recall = latest_recall["metric_value"] if latest_recall else 0

    # 最新的 Faithfulness
    latest_faithfulness = conn.execute(
        """
        SELECT metric_value FROM evaluation_metrics
        WHERE metric_name = 'faithfulness'
        ORDER BY created_at DESC LIMIT 1
        """
    ).fetchone()
    latest_faithfulness = latest_faithfulness["metric_value"] if latest_faithfulness else 0

    # 最新的 Hallucination Rate
    latest_hallucination = conn.execute(
        """
        SELECT metric_value FROM evaluation_metrics
        WHERE metric_name = 'hallucination_rate'
        ORDER BY created_at DESC LIMIT 1
        """
    ).fetchone()
    latest_hallucination = latest_hallucination["metric_value"] if latest_hallucination else 0

    # 总运行次数
    total_runs = conn.execute(
        "SELECT COUNT(*) as count FROM benchmark_runs"
    ).fetchone()["count"]

    # 成功运行次数
    successful_runs = conn.execute(
        "SELECT COUNT(*) as count FROM benchmark_runs WHERE status = 'completed'"
    ).fetchone()["count"]

    return {
        "latest_recall_at_3": round(latest_recall * 100, 2),
        "latest_faithfulness": round(latest_faithfulness * 100, 2),
        "latest_hallucination_rate": round(latest_hallucination * 100, 2),
        "total_runs": total_runs,
        "successful_runs": successful_runs,
        "success_rate": round((successful_runs / total_runs * 100) if total_runs > 0 else 0, 2),
    }
