"""Observability Layer - Query Trace 和 Distributed Tracing"""
import asyncio
import time
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()

# ── Re-export insert_query_trace for callers who imported from this module ──


async def _safe_pg_insert(trace_data: dict) -> None:
    """Best-effort async insert into PostgreSQL query_traces table."""
    try:
        from app.memory.pg import insert_query_trace  # noqa: WPS433
        await insert_query_trace(trace_data)
    except Exception as exc:
        logger.warning("pg_trace_insert_failed", error=str(exc))


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
        """Build the trace, persist to PostgreSQL asynchronously
        when the PG adapter is available.  Safe to call from sync contexts —
        the async write is fire-and-forget.

        Returns the built :class:`QueryTrace`.
        """
        trace = self.build_trace()

        try:
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


__all__ = ["QueryTrace", "QueryTracer", "_safe_pg_insert"]
