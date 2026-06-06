import asyncio
import logging
import os
import sys
import threading
import time
import uuid

# Suppress noisy ChromaDB telemetry errors
logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
import structlog

from app.api.models import StatusResponse
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
from app.exceptions import AureonException
from app.routers import chat as chat_router
from app.routers import rag as rag_router
from app.routers import crew as crew_router
from app.agent.llm import create_llm
from app.tools import ALL_TOOLS
from app.memory.db import init_db
from app.memory.manager import manager as memory_manager
from app.config import settings
from app.cache.redis_client import close_redis
from app.common import SSE_HEADERS

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

app = FastAPI(title="Aureon API", version="0.1.0")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# ── Prometheus metrics ──
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


# ── Custom exception handler (structured JSON) ──
from fastapi.responses import JSONResponse


@app.exception_handler(AureonException)
async def aureon_exception_handler(request: Request, exc: AureonException):
    """Return structured JSON for all Aureon-specific exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_type,
            "detail": str(exc.detail),
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
        public_paths = {"/api/health", "/api/crew/health", "/metrics"}
        if request.url.path not in public_paths:
            api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key", "")
            if not api_key:
                return JSONResponse(
                    status_code=401,
                    content={"error": "unauthorized", "detail": "Missing API key. Provide X-API-Key header or api_key query parameter."},
                )
            if api_key != settings.api_auth_key:
                return JSONResponse(
                    status_code=403,
                    content={"error": "forbidden", "detail": "Invalid API key."},
                )

    start = time.time()
    response = await call_next(request)
    elapsed = int((time.time() - start) * 1000)

    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    logger.info(
        "request_completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        elapsed_ms=elapsed,
    )
    return response


def _warmup_bm25():
    """Build BM25 index and auto-rebuild vector index if empty.

    Runs in background thread at startup. Non-blocking.
    When index is empty (e.g. after Railway restart), automatically
    rebuilds using API embedding — no local BGE model, no OOM.
    """
    global _bm25_warmup_done, _index_ready
    try:
        from app.rag.vector_store import _build_kw_index, check_index_stale, get_collection_stats
        _build_kw_index()
        logger.info("BM25 index warmup complete")

        # Check if vector index needs rebuild
        base_dir = os.path.dirname(os.path.dirname(__file__))
        articles_dir = os.path.join(base_dir, "data", "articles")
        status = check_index_stale(articles_dir)
        doc_count, chunk_count = get_collection_stats()

        if status["stale"] and doc_count == 0:
            # Index empty — auto-rebuild via API embedding (no local model, no OOM)
            logger.info("Index empty, auto-rebuilding via API embedding...")
            try:
                from app.rag.qa_chain import run_index_pipeline
                result = run_index_pipeline(articles_dir)
                logger.info("Auto-rebuild complete: %d docs, %d chunks, %.1fs",
                            result.get("documents_indexed", 0),
                            result.get("chunks_created", 0),
                            result.get("elapsed_seconds", 0))
            except Exception as e:
                logger.error("Auto-rebuild failed: %s", e)
        else:
            logger.info("Index OK: %d docs, %d chunks", doc_count, chunk_count)
    except Exception as e:
        logger.warning("BM25 warmup / index check failed (non-fatal): %s", e)
    finally:
        _index_ready = True
        _bm25_warmup_done = True


_bm25_warmup_done = False  # starts False; background thread sets True when ready
_index_ready = False  # True once index check completes


@app.on_event("startup")
async def startup():
    if not settings.llm_api_key and not settings.fallback_api_key:
        logger.warning("LLM_API_KEY 未配置，Agent 调用将失败")
    if settings.langchain_api_key:
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.langchain_api_key)
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.langchain_project)
        os.environ.setdefault("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
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
    memory_manager.init_background_tasks()

    # Background BM25 + ChromaDB warmup + auto-rebuild (non-blocking)
    threading.Thread(target=_warmup_bm25, daemon=True).start()

    logger.info("Startup complete")


@app.on_event("shutdown")
async def shutdown():
    memory_manager.flush_all_scenarios()
    await close_redis()


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


app.include_router(chat_router.router)
app.include_router(rag_router.router)
app.include_router(crew_router.router)
app.include_router(stats_router)
app.include_router(analytics_router)
app.include_router(feature_flags_router)
app.include_router(observability_router)
app.include_router(security_router)
app.include_router(evaluation_router)
app.include_router(cost_router)
app.include_router(reliability_router)
app.include_router(knowledge_router)
app.include_router(ai_platform_router)
app.include_router(integration_router)

# ── SPA 静态文件（必须在 API 路由之后） ──
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    logger.warning("Static directory not found", path=os.path.abspath(static_dir))
# redeploy trigger
