"""Observability Layer - Query Trace 和 Distributed Tracing"""
import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()


class QueryTrace(BaseModel):
    """查询追踪数据模型"""
    id: Optional[int] = None
    request_id: str = Field(..., description="请求 ID")
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    workspace_id: Optional[str] = None
    query: str = Field(..., description="查询内容")
    retrieval_latency_ms: float = 0.0
    rerank_latency_ms: float = 0.0
    llm_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    token_usage_input: int = 0
    token_usage_output: int = 0
    cache_hit: bool = False
    retrieved_documents: list[dict] = []
    cited_documents: list[dict] = []
    confidence_score: Optional[float] = None
    status: str = "pending"
    error_message: Optional[str] = None
    created_at: Optional[str] = None


class QueryTracer:
    """查询追踪器"""

    def __init__(self, request_id: str, query: str = "", session_id: Optional[str] = None):
        self.request_id = request_id
        self.query = query
        self.session_id = session_id
        self.start_time = time.time()
        self.retrieval_start = None
        self.retrieval_end = None
        self.rerank_start = None
        self.rerank_end = None
        self.llm_start = None
        self.llm_end = None
        self.cache_hit = False
        self.retrieved_documents = []
        self.cited_documents = []
        self.token_usage_input = 0
        self.token_usage_output = 0
        self.confidence_score = None

    def start_retrieval(self):
        """开始检索阶段"""
        self.retrieval_start = time.time()

    def end_retrieval(self, documents: list[dict]):
        """结束检索阶段"""
        self.retrieval_end = time.time()
        self.retrieved_documents = documents

    def start_rerank(self):
        """开始重排阶段"""
        self.rerank_start = time.time()

    def end_rerank(self, documents: list[dict]):
        """结束重排阶段"""
        self.rerank_end = time.time()
        self.cited_documents = documents

    def start_llm(self):
        """开始 LLM 阶段"""
        self.llm_start = time.time()

    def end_llm(self, token_input: int = 0, token_output: int = 0):
        """结束 LLM 阶段"""
        self.llm_end = time.time()
        self.token_usage_input = token_input
        self.token_usage_output = token_output

    def set_cache_hit(self, hit: bool):
        """设置缓存命中状态"""
        self.cache_hit = hit

    def set_confidence_score(self, score: float):
        """设置置信度分数"""
        self.confidence_score = score

    def build_trace(self) -> QueryTrace:
        """构建追踪数据"""
        total_latency = (time.time() - self.start_time) * 1000
        retrieval_latency = (
            (self.retrieval_end - self.retrieval_start) * 1000
            if self.retrieval_start and self.retrieval_end
            else 0
        )
        rerank_latency = (
            (self.rerank_end - self.rerank_start) * 1000
            if self.rerank_start and self.rerank_end
            else 0
        )
        llm_latency = (
            (self.llm_end - self.llm_start) * 1000
            if self.llm_start and self.llm_end
            else 0
        )

        return QueryTrace(
            request_id=self.request_id,
            session_id=self.session_id,
            query=self.query,
            retrieval_latency_ms=retrieval_latency,
            rerank_latency_ms=rerank_latency,
            llm_latency_ms=llm_latency,
            total_latency_ms=total_latency,
            token_usage_input=self.token_usage_input,
            token_usage_output=self.token_usage_output,
            cache_hit=self.cache_hit,
            retrieved_documents=self.retrieved_documents,
            cited_documents=self.cited_documents,
            confidence_score=self.confidence_score,
            status="completed",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def record(self) -> QueryTrace:
        """Build the trace, persist to SQLite, and asynchronously
        write to PostgreSQL when the PG adapter is available.

        Returns the built :class:`QueryTrace`.
        """
        trace = self.build_trace()

        # 1. Synchronous SQLite persist (always available)
        try:
            save_query_trace(trace)
        except Exception as exc:
            logger.warning("sqlite_trace_save_failed", error=str(exc))

        # 2. Best-effort async PG write
        try:
            from app.memory.pg import insert_query_trace  # noqa: WPS433

            pg_data: dict = {
                "request_id": trace.request_id,
                "session_id": trace.session_id,
                "user_id": trace.user_id,
                "workspace_id": trace.workspace_id,
                "query": trace.query,
                "latency_ms": trace.total_latency_ms,
                "cache_hit": trace.cache_hit,
                "retrieval_latency_ms": trace.retrieval_latency_ms,
                "rerank_latency_ms": trace.rerank_latency_ms,
                "llm_latency_ms": trace.llm_latency_ms,
                "total_chunks": len(trace.retrieved_documents),
                "reranked_chunks": len(trace.cited_documents),
            }
            loop = asyncio.get_running_loop()
            loop.create_task(_safe_pg_insert(pg_data))
        except RuntimeError:
            # No running event-loop (e.g. called from a sync context)
            logger.debug("pg_write_skipped_no_event_loop")
        except Exception as exc:
            logger.warning("pg_trace_write_failed", error=str(exc))

        return trace


async def _safe_pg_insert(trace_data: dict) -> None:
    """Best-effort async insert into PostgreSQL query_traces table."""
    try:
        from app.memory.pg import insert_query_trace  # noqa: WPS433
        await insert_query_trace(trace_data)
    except Exception as exc:
        logger.warning("pg_trace_insert_failed", error=str(exc))


def init_query_traces_table():
    """初始化 Query Traces 表"""
    from app.memory.db import get_db

    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT UNIQUE NOT NULL,
            session_id TEXT,
            user_id TEXT,
            workspace_id TEXT,
            query TEXT NOT NULL,
            retrieval_latency_ms REAL DEFAULT 0,
            rerank_latency_ms REAL DEFAULT 0,
            llm_latency_ms REAL DEFAULT 0,
            total_latency_ms REAL DEFAULT 0,
            token_usage_input INTEGER DEFAULT 0,
            token_usage_output INTEGER DEFAULT 0,
            cache_hit BOOLEAN DEFAULT 0,
            retrieved_documents TEXT,
            cited_documents TEXT,
            confidence_score REAL,
            status TEXT DEFAULT 'pending',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_query_traces_request_id ON query_traces(request_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_query_traces_created_at ON query_traces(created_at)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_query_traces_status ON query_traces(status)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_query_traces_status_created_at ON query_traces(status, created_at)
    """)
    conn.commit()


def save_query_trace(trace: QueryTrace) -> int:
    """保存查询追踪"""
    import json
    from app.memory.db import get_db

    conn = get_db()
    cursor = conn.execute(
        """
        INSERT INTO query_traces (
            request_id, session_id, user_id, workspace_id, query,
            retrieval_latency_ms, rerank_latency_ms, llm_latency_ms, total_latency_ms,
            token_usage_input, token_usage_output, cache_hit,
            retrieved_documents, cited_documents, confidence_score,
            status, error_message, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trace.request_id,
            trace.session_id,
            trace.user_id,
            trace.workspace_id,
            trace.query,
            trace.retrieval_latency_ms,
            trace.rerank_latency_ms,
            trace.llm_latency_ms,
            trace.total_latency_ms,
            trace.token_usage_input,
            trace.token_usage_output,
            trace.cache_hit,
            json.dumps(trace.retrieved_documents),
            json.dumps(trace.cited_documents),
            trace.confidence_score,
            trace.status,
            trace.error_message,
            trace.created_at,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_recent_traces(limit: int = 100) -> list[QueryTrace]:
    """获取最近的查询追踪"""
    import json
    from app.memory.db import get_db

    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM query_traces ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()

    return [
        QueryTrace(
            id=row["id"],
            request_id=row["request_id"],
            session_id=row["session_id"],
            user_id=row["user_id"],
            workspace_id=row["workspace_id"],
            query=row["query"],
            retrieval_latency_ms=row["retrieval_latency_ms"],
            rerank_latency_ms=row["rerank_latency_ms"],
            llm_latency_ms=row["llm_latency_ms"],
            total_latency_ms=row["total_latency_ms"],
            token_usage_input=row["token_usage_input"],
            token_usage_output=row["token_usage_output"],
            cache_hit=bool(row["cache_hit"]),
            retrieved_documents=json.loads(row["retrieved_documents"]) if row["retrieved_documents"] else [],
            cited_documents=json.loads(row["cited_documents"]) if row["cited_documents"] else [],
            confidence_score=row["confidence_score"],
            status=row["status"],
            error_message=row["error_message"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_trace_stats() -> dict:
    """获取追踪统计数据"""
    from app.memory.db import get_db

    conn = get_db()

    # 总请求数
    total = conn.execute("SELECT COUNT(*) as count FROM query_traces").fetchone()["count"]

    # 成功/失败数
    success = conn.execute(
        "SELECT COUNT(*) as count FROM query_traces WHERE status = 'completed'"
    ).fetchone()["count"]
    failed = conn.execute(
        "SELECT COUNT(*) as count FROM query_traces WHERE status = 'failed'"
    ).fetchone()["count"]

    # 缓存命中率
    cache_hits = conn.execute(
        "SELECT COUNT(*) as count FROM query_traces WHERE cache_hit = 1"
    ).fetchone()["count"]

    # 平均延迟
    avg_total_latency = conn.execute(
        "SELECT AVG(total_latency_ms) as avg FROM query_traces WHERE status = 'completed'"
    ).fetchone()["avg"] or 0

    avg_retrieval_latency = conn.execute(
        "SELECT AVG(retrieval_latency_ms) as avg FROM query_traces WHERE status = 'completed'"
    ).fetchone()["avg"] or 0

    avg_llm_latency = conn.execute(
        "SELECT AVG(llm_latency_ms) as avg FROM query_traces WHERE status = 'completed'"
    ).fetchone()["avg"] or 0

    # P95 延迟
    p95_total_latency = conn.execute(
        """
        SELECT total_latency_ms as p95 FROM query_traces
        WHERE status = 'completed'
        ORDER BY total_latency_ms
        LIMIT 1 OFFSET (SELECT CAST(COUNT(*) * 0.95 AS INTEGER) FROM query_traces WHERE status = 'completed')
        """
    ).fetchone()
    p95_total_latency = p95_total_latency["p95"] if p95_total_latency else 0

    # Token 使用统计
    total_tokens_input = conn.execute(
        "SELECT SUM(token_usage_input) as total FROM query_traces WHERE status = 'completed'"
    ).fetchone()["total"] or 0
    total_tokens_output = conn.execute(
        "SELECT SUM(token_usage_output) as total FROM query_traces WHERE status = 'completed'"
    ).fetchone()["total"] or 0

    return {
        "total_requests": total,
        "success_count": success,
        "failed_count": failed,
        "success_rate": (success / total * 100) if total > 0 else 0,
        "cache_hit_rate": (cache_hits / total * 100) if total > 0 else 0,
        "avg_total_latency_ms": round(avg_total_latency, 2),
        "avg_retrieval_latency_ms": round(avg_retrieval_latency, 2),
        "avg_llm_latency_ms": round(avg_llm_latency, 2),
        "p95_total_latency_ms": round(p95_total_latency, 2),
        "total_tokens_input": total_tokens_input,
        "total_tokens_output": total_tokens_output,
    }
