import logging
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.routing import Match, Mount

# ── CrossEncoder safety patch (MUST be early — patches sentence_transformers) ──
import app.startup.cross_encoder  # noqa: F401

import prometheus_fastapi_instrumentator.routing as _pfi_routing

from app.api.analytics import router as analytics_router
from app.api.rag_stats import router as stats_router
from app.api.websocket_chat import router as websocket_chat_router
from app.api.ws_dashboard import router as ws_dashboard_router
from app.audit.router import router as audit_router
from app.config import settings
from app.cost.router import router as cost_router
from app.evaluation.router import router as evaluation_router
from app.exceptions import AureonException
from app.features.router import router as feature_flags_router
from app.integration.router import router as integration_router
from app.knowledge.router import router as knowledge_router
from app.ai_platform.router import router as ai_platform_router
from app.middleware.logging import logging_middleware
from app.multi_tenant.middleware import TenantMiddleware
from app.observability.router import router as observability_router
from app.reliability.router import router as reliability_router
from app.routers import chat as chat_router
from app.routers import crew as crew_router
from app.routers import rag as rag_router
from app.security.roles_router import router as roles_router
from app.security.router import router as security_router
from app.security.users_router import router as users_router
from app.startup import warmup
from app.startup.lifespan import lifespan
from app.tools import ALL_TOOLS

# ── Prometheus instrumentator FastAPI 0.137 compat patch ──
# FastAPI 0.137 changed app.routes from flat list to tree with _IncludedRouter nodes.
# prometheus_fastapi_instrumentator.routing._get_route_name accesses route.path,
# which _IncludedRouter doesn't have. Patch to skip non-leaf nodes and recurse.


def _patched_get_route_name(scope, routes, route_name=None):
    """Compat patch: skip _IncludedRouter (no .path), recurse into .routes if present."""
    for route in routes:
        # FastAPI 0.137+ _IncludedRouter has .routes but no .path
        if not hasattr(route, "path"):
            if hasattr(route, "routes"):
                child_name = _patched_get_route_name(scope, route.routes, route_name)
                if child_name is not None:
                    return child_name
            continue
        match, child_scope = route.matches(scope)
        if match == Match.FULL:
            route_name = route.path
            child_scope = {**scope, **child_scope}
            if isinstance(route, Mount) and route.routes:
                child_route_name = _patched_get_route_name(child_scope, route.routes, route_name)
                if child_route_name is None:
                    route_name = None
                else:
                    route_name += child_route_name
            return route_name
        elif match == Match.PARTIAL and route_name is None:
            route_name = route.path
    return None


_pfi_routing._get_route_name = _patched_get_route_name

# Suppress noisy telemetry
logging.getLogger("urllib3").setLevel(logging.WARNING)

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

# CORS allowed headers whitelist (not ["*"] to prevent header forgery)
_CORS_ALLOWED_HEADERS = [
    "Authorization",
    "Content-Type",
    "X-Request-ID",
    "X-API-Key",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=_CORS_ALLOWED_HEADERS,
    max_age=600,
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
app.include_router(ws_dashboard_router, tags=["websocket"])
app.include_router(users_router)
app.include_router(roles_router)

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
