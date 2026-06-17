import logging
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor

# ── CrossEncoder safety patch (MUST be first — patches sentence_transformers) ──
import app.startup.cross_encoder  # noqa: F401

# Suppress noisy telemetry
logging.getLogger("urllib3").setLevel(logging.WARNING)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from pydantic import BaseModel, Field
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
from app.exceptions import AureonException
from app.routers import chat as chat_router
from app.routers import rag as rag_router
from app.routers import crew as crew_router
from app.tools import ALL_TOOLS
from app.config import settings
from app.multi_tenant.middleware import TenantMiddleware
from app.startup.lifespan import lifespan
from app.startup import warmup
from app.middleware.logging import logging_middleware

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

app = FastAPI(
    title="Aureon API",
    version=os.environ.get("BUILD_VERSION", "0.1.0"),
    lifespan=lifespan,
)

# ── Custom ThreadPoolExecutor for async routes ──
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
app.add_middleware(TenantMiddleware)

# ── Prometheus metrics ──
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


# ── Custom exception handler (structured JSON) ──
@app.exception_handler(AureonException)
async def aureon_exception_handler(request: Request, exc: AureonException):
    """Return structured JSON for all Aureon-specific exceptions."""
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


# ── Logging middleware (extracted to app.middleware.logging) ──
app.middleware("http")(logging_middleware)


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
        "status": "ok" if warmup.bm25_warmup_done else "warming_up",
        "model": settings.llm_model,
        "tools": [t.name for t in ALL_TOOLS] if warmup.bm25_warmup_done else [],
        "index_ready": warmup.index_ready,
    }


@app.get("/health/ready")
async def health_ready():
    """Readiness probe — checks if dependency services are reachable."""
    checks = {"index_ready": warmup.index_ready}
    try:
        from app.cache.redis_client import get_redis
        r = get_redis()
        if r:
            await r.ping()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "skipped"
    except Exception as e:
        checks["redis"] = f"error: {e}"
    all_ok = warmup.index_ready and checks.get("redis") in ("ok", "skipped")
    return {"status": "ready" if all_ok else "not_ready", "checks": checks}


# ── Core routes (always registered) ──
app.include_router(chat_router.router, prefix="/api/chat", tags=["chat"])
app.include_router(rag_router.router, prefix="/api/rag", tags=["rag"])
app.include_router(crew_router.router, prefix="/api/crew", tags=["crew"])
app.include_router(stats_router)
app.include_router(analytics_router)
app.include_router(feature_flags_router)
app.include_router(observability_router, prefix="/api/observability")
app.include_router(security_router, prefix="/api/security")
app.include_router(audit_router, prefix="/api/audit")
app.include_router(websocket_chat_router, tags=["websocket"])

# ── Experimental routes (conditional on EXPERIMENTAL_MODULES env var) ──
if os.environ.get("EXPERIMENTAL_MODULES", "true").lower() != "false":
    app.include_router(evaluation_router)
    app.include_router(cost_router)
    app.include_router(reliability_router)
    app.include_router(knowledge_router, prefix="/api/knowledge")
    app.include_router(ai_platform_router)
    app.include_router(integration_router)

# ── SPA 静态文件（必须在 API 路由之后） ──
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    logger.warning("Static directory not found", path=os.path.abspath(static_dir))
