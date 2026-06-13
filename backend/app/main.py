import hmac
import logging
import os
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

# Suppress noisy telemetry
logging.getLogger("urllib3").setLevel(logging.WARNING)

# ── Safety: prevent CrossEncoder OOM on constrained environments ──
from app.config import settings as _cfg
_rerank_disabled = not _cfg.rerank.rerank_enabled
if _rerank_disabled:
    try:
        import sentence_transformers as _st
        _OrigCE = _st.CrossEncoder
        class _DisabledCrossEncoder:
            """Stub that prevents CrossEncoder from loading (avoids OOM on Railway)."""
            def __init__(self, *args, **kwargs):
                raise RuntimeError(
                    "CrossEncoder disabled (RERANK_ENABLED=false). "
                    "Set RERANK_ENABLED=true or increase memory to enable reranking."
                )
            def __getattr__(self, name):
                raise RuntimeError("CrossEncoder disabled (RERANK_ENABLED=false)")
        _st.CrossEncoder = _DisabledCrossEncoder
        import structlog
        structlog.get_logger().info("CrossEncoder disabled via RERANK_ENABLED=false")
    except ImportError:
        pass  # sentence-transformers not installed, nothing to patch

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
import structlog

from app.api.rag_stats import router as stats_router
from app.api.analytics import router as analytics_router
from app.features.router import router as feature_flags_router
from app.observability.router import router as observability_router
from app.security.router import router as security_router
from app.evaluation.router import router as evaluation_router
from app.cost.router import router as cost_router
from app.reliability.router import router as reliability_router
from app.knowledge.router import router as knowledge_router
from app.ai_platform.router import router as ai_platform_router
from app.integration.router import router as integration_router
from app.audit.router import router as audit_router
from app.api.websocket_chat import router as websocket_chat_router
from app.exceptions import (
    AureonException,
)
from app.routers import chat as chat_router
from app.routers import rag as rag_router
from app.routers import crew as crew_router
from app.tools import ALL_TOOLS
from app.memory.db import init_db, close_db
from app.memory.manager import manager as memory_manager
from app.config import settings
from app.cache.redis_client import close_redis
from app.multi_tenant.middleware import TenantMiddleware

# ── CrewAI (merged, lazy-imported in route handlers) ──
from pydantic import BaseModel, Field

# ── Structured logging (replaces stdlib logging) ──
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer()
        if sys.stdout.isatty()
        else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# ── Rate limiter ──
limiter = Limiter(key_func=get_remote_address)

# ── Global state for health checks ──
_bm25_warmup_done = False  # starts False; background thread sets True when ready
_index_ready = False  # True once index check completes


def _warmup_bm25():
    """Build BM25 index and auto-rebuild vector index if empty or config mismatch.

    Runs in background thread at startup. Non-blocking.
    Uses check_index_upgrade_strategy to determine:
    - skip: index is up-to-date, no action needed
    - rebuild: full rebuild (vector structure/model changed)
    - incremental: only add/remove changed files
    """
    global _bm25_warmup_done, _index_ready
    try:
        from app.rag.vector_store import check_index_upgrade_strategy, get_collection_stats

        # 确保 Qdrant Payload 索引存在（生产环境兼容）
        try:
            from app.rag.vector_store import ensure_payload_indexes
            ensure_payload_indexes()
        except Exception as e:
            logger.warning("Payload index check failed (non-fatal): %s", e)

        # 分析索引升级策略
        base_dir = os.path.dirname(os.path.dirname(__file__))
        articles_dir = os.path.join(base_dir, "data", "articles")
        strategy = check_index_upgrade_strategy(articles_dir=articles_dir)

        if strategy["action"] == "skip":
            doc_count, chunk_count = get_collection_stats()
            logger.info("Index OK (skip): %d docs, %d chunks — %s", doc_count, chunk_count, strategy["reason"])
        elif strategy["action"] == "rebuild":
            logger.info("Index rebuild triggered: %s", strategy["reason"])
            try:
                from app.rag.qa_chain import run_index_pipeline
                result = run_index_pipeline(articles_dir)
                logger.info("Auto-rebuild complete: %d docs, %d chunks, %.1fs",
                            result.get("documents_indexed", 0),
                            result.get("chunks_created", 0),
                            result.get("elapsed_seconds", 0))
            except Exception as e:
                logger.error("Auto-rebuild failed: %s", e)
        elif strategy["action"] == "incremental":
            logger.info("Incremental update: %s", strategy["reason"])
            try:
                _incremental_update(strategy, articles_dir)
            except Exception as e:
                logger.error("Incremental update failed, falling back to full rebuild: %s", e)
                try:
                    from app.rag.qa_chain import run_index_pipeline
                    result = run_index_pipeline(articles_dir)
                    logger.info("Fallback rebuild complete: %d docs, %d chunks, %.1fs",
                                result.get("documents_indexed", 0),
                                result.get("chunks_created", 0),
                                result.get("elapsed_seconds", 0))
                except Exception as e2:
                    logger.error("Fallback rebuild also failed: %s", e2)

        # Eagerly load GPU models for faster first-request latency
        try:
            from app.rag.embed_gpu import eager_load_models
            eager_load_models()
        except Exception as e:
            logger.warning("GPU model eager loading failed (non-fatal): %s", e)

    except Exception as e:
        logger.warning("BM25 warmup / index check failed (non-fatal): %s", e)
    finally:
        _index_ready = True
        _bm25_warmup_done = True


def _incremental_update(strategy: dict, articles_dir: str):
    """执行增量索引更新：删除移除的文件，添加新增的文件。"""
    from app.rag.vector_store import delete_from_index, add_to_index
    from app.rag.loader import load_markdown_files

    # 1. 删除已移除的文件
    for filename in strategy["files_to_del"]:
        try:
            delete_from_index(filename)
            logger.info("Incremental: deleted '%s'", filename)
        except Exception as e:
            logger.warning("Incremental: failed to delete '%s': %s", filename, e)

    # 2. 加载并添加新增的文件
    if strategy["files_to_add"]:
        try:
            from langchain.text_splitter import RecursiveCharacterTextSplitter
        except ImportError:
            from langchain_text_splitters import RecursiveCharacterTextSplitter

        # 加载全部文件，然后过滤出需要新增的
        all_docs = load_markdown_files(articles_dir)
        add_set = set(strategy["files_to_add"])
        new_docs = [d for d in all_docs if d["metadata"].get("source", "") in add_set]

        all_chunks = []
        for doc in new_docs:
            parent_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1500, chunk_overlap=100,
                separators=["\n## ", "\n### ", "\n\n", "\n", " ", ""],
            )
            child_splitter = RecursiveCharacterTextSplitter(
                chunk_size=512, chunk_overlap=50,
                separators=["\n", " ", ""],
            )

            parents = parent_splitter.split_text(doc["content"])
            for parent_idx, parent_text in enumerate(parents):
                children = child_splitter.split_text(parent_text)
                for child_text in children:
                    all_chunks.append({
                        "text": child_text,
                        "metadata": {
                            **doc["metadata"],
                            "parent_text": parent_text,
                            "parent_idx": parent_idx,
                        },
                    })

        if all_chunks:
            add_to_index(all_chunks)
            logger.info("Incremental: added %d chunks from %d new files",
                        len(all_chunks), len(new_docs))


from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown logic."""
    # ── Startup ──
    if not settings.llm_api_key and not settings.fallback_api_key:
        logger.warning("LLM_API_KEY 未配置，Agent 调用将失败")
    # 显式禁用 LangSmith（防止 Railway 平台环境变量自动激活导致 403）
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    init_db()
    from app.features import init_feature_flags_table
    from app.observability import init_query_traces_table
    from app.security import init_pii_detection_table, init_sso_providers_table
    from app.evaluation import init_evaluation_tables
    from app.cost import init_cost_tables
    from app.reliability import init_reliability_tables
    from app.knowledge import init_knowledge_tables
    from app.ai_platform import init_ai_platform_tables
    from app.integration import init_integration_tables
    from app.audit import init_audit_tables
    from app.memory.pg import init_pg_tables
    init_feature_flags_table()
    init_query_traces_table()
    init_pii_detection_table()
    init_sso_providers_table()
    init_evaluation_tables()
    init_cost_tables()
    init_reliability_tables()
    init_knowledge_tables()
    init_ai_platform_tables()
    init_integration_tables()
    init_audit_tables()
    await init_pg_tables()
    memory_manager.init_background_tasks()

    # Background BM25 + ChromaDB warmup + auto-rebuild (non-blocking)
    threading.Thread(target=_warmup_bm25, daemon=True).start()

    # OpenTelemetry distributed tracing
    try:
        from app.observability.tracing import init_tracing
        init_tracing(app)
    except Exception as e:
        logger.warning("OpenTelemetry tracing init failed (non-fatal): %s", e)

    # Langfuse tracing (async check)
    try:
        from app.observability.langfuse_integration import init_langfuse
        await init_langfuse()
    except Exception as e:
        logger.warning("Langfuse init failed (non-fatal): %s", e)

    logger.info("Startup complete")

    yield  # Application runs here

    # ── Shutdown ──
    # Flush Langfuse traces
    try:
        from app.observability.langfuse_integration import shutdown_langfuse
        await shutdown_langfuse()
    except Exception as e:
        logger.warning("Langfuse shutdown failed (non-fatal): %s", e)
    memory_manager.flush_all_scenarios()
    close_db()
    await close_redis()


app = FastAPI(
    title="Aureon API",
    version=os.environ.get("BUILD_VERSION", "0.1.0"),
    lifespan=lifespan,
)

# ── Custom ThreadPoolExecutor for async routes ──
# Configure max_workers to handle concurrent requests across multiple Uvicorn workers
executor = ThreadPoolExecutor(max_workers=64)
app.state.executor = executor

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# ── Tenant Middleware (multi-tenant isolation) ──
app.add_middleware(TenantMiddleware)

# ── Prometheus metrics ──
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


# ── Custom exception handler (structured JSON) ──
from fastapi.responses import JSONResponse


@app.exception_handler(AureonException)
async def aureon_exception_handler(request: Request, exc: AureonException):
    """Return structured JSON for all Aureon-specific exceptions.

    Includes ``request_id`` from the structlog contextvars so that
    frontend logs can be correlated with backend traces.
    """
    # Retrieve request_id from structlog context (set by logging_middleware)
    request_id = structlog.contextvars.get_contextvars().get("request_id", str(uuid.uuid4())[:8])
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_type,
            "detail": str(exc.detail),
            "request_id": request_id,
            "error_type": exc.error_type,
        },
    )


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Inject request_id + security headers + optional auth, log request completion."""
    request_id = str(uuid.uuid4())[:8]
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    # API Key authentication (skip when API_AUTH_KEY is not configured)
    if settings.api_auth_key and request.url.path.startswith("/api/"):
        # Public endpoints that don't require auth
        public_paths = {"/api/health", "/api/crew/health", "/metrics", "/api/security/sso/login"}
        if request.url.path not in public_paths:
            api_key = request.headers.get("X-API-Key")
            if not api_key:
                return JSONResponse(
                    status_code=401,
                    content={"error": "unauthorized", "detail": "Missing API key. Provide X-API-Key header."},
                )
            if not hmac.compare_digest(api_key, settings.api_auth_key):
                return JSONResponse(
                    status_code=403,
                    content={"error": "forbidden", "detail": "Invalid API key."},
                )

    start = time.time()
    try:
        response = await call_next(request)
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        logger.error("unhandled_exception", path=request.url.path, error=str(e)[:200], elapsed_ms=elapsed)
        return JSONResponse(
            status_code=503,
            content={
                "error": "service_unavailable",
                "detail": "Request processing failed. Please try again.",
                "request_id": request_id,
            },
        )
    elapsed = int((time.time() - start) * 1000)

    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"

    logger.info(
        "request_completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        elapsed_ms=elapsed,
    )
    return response


class LangGraphRunRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)
    session_id: str = Field(default="", max_length=100)


@app.post("/api/langgraph/run")
@limiter.limit("5/minute")
async def langgraph_run(req: LangGraphRunRequest, request: Request):
    """Run LangGraph workflow for complex tasks."""
    from app.langgraph.graph import run_workflow

    result = await run_workflow(req.query, session_id=req.session_id or None)
    return result


@app.get("/api/health")
async def health():
    return {
        "status": "ok" if _bm25_warmup_done else "warming_up",
        "model": settings.llm_model,
        "tools": [t.name for t in ALL_TOOLS] if _bm25_warmup_done else [],
        "index_ready": _index_ready,
    }


@app.get("/health/ready")
async def health_ready():
    """Readiness probe — checks if dependency services are reachable."""
    checks = {"index_ready": _index_ready}
    # Lightweight Redis check
    try:
        from app.cache.redis_client import get_redis
        r = get_redis()
        if r:
            r.ping()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "skipped"
    except Exception as e:
        checks["redis"] = f"error: {e}"
    all_ok = _index_ready and checks.get("redis") in ("ok", "skipped")
    return {"status": "ready" if all_ok else "not_ready", "checks": checks}


# ── Legacy /api/ routes (backward compatible, kept alongside /api/v1/) ──
app.include_router(chat_router.router, prefix="/api/chat", tags=["chat"])
app.include_router(rag_router.router, prefix="/api/rag", tags=["rag"])
app.include_router(crew_router.router, prefix="/api/crew", tags=["crew"])
app.include_router(stats_router)  # rag_stats.py has no prefix, routes handle /api/* internally
app.include_router(analytics_router)  # already has prefix=/api/rag/analytics
app.include_router(feature_flags_router)  # already has prefix=/api/feature-flags
app.include_router(observability_router, prefix="/api/observability")  # routes use relative paths
app.include_router(security_router, prefix="/api/security")  # routes use relative paths
app.include_router(evaluation_router)  # already has prefix=/api/evaluation
app.include_router(cost_router)  # already has prefix=/api/cost
app.include_router(reliability_router)  # already has prefix=/api/reliability
app.include_router(knowledge_router, prefix="/api/knowledge")  # routes use relative paths
app.include_router(ai_platform_router)  # already has prefix=/api/ai-platform
app.include_router(integration_router)  # already has prefix=/api/integration
app.include_router(audit_router, prefix="/api/audit")  # routes use relative paths
app.include_router(websocket_chat_router, tags=["websocket"])

# ── SPA 静态文件（必须在 API 路由之后） ──
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    logger.warning("Static directory not found", path=os.path.abspath(static_dir))
# redeploy trigger
