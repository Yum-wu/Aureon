import logging
import os
import secrets
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor

import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.rate_limit import limiter


# ── CrossEncoder safety patch (MUST be early — patches sentence_transformers) ──
import app.startup.cross_encoder  # noqa: F401

from app.api.analytics import router as analytics_router
from app.api.cost import router as cost_router
from app.api.feature_flags import router as feature_flags_router
from app.api.rag_stats import router as stats_router
from app.api.websocket_chat import router as websocket_chat_router
from app.api.ws_dashboard import router as ws_dashboard_router
from app.audit.router import router as audit_router
from app.config import settings
from app.exceptions import AureonException
from app.middleware.logging import logging_middleware
from app.multi_tenant.middleware import TenantMiddleware
from app.observability.router import router as observability_router
from app.reliability.router import router as reliability_router
from app.routers import chat as chat_router
from app.routers import crew as crew_router
from app.routers import rag as rag_router
from app.routers.support import router as support_router
from app.security.roles_router import router as roles_router
from app.security.router import router as security_router
from app.security.users_router import router as users_router
from app.security.rbac import require_role, UserRole
from app.startup import warmup
from app.startup.lifespan import lifespan
from app.tools import ALL_TOOLS


# ── Security headers middleware (S6: CSP + S12: CSP Nonce) ──
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # S12: 为每个请求生成随机 nonce，用于 CSP nonce-based strict policy
        nonce = secrets.token_hex(16)
        request.state.csp_nonce = nonce

        response = await call_next(request)
        # CSP header 的 script-src 使用 nonce，同时保留 'self' 允许同源脚本加载
        # 这样既支持 nonce 又不破坏现有静态脚本加载（SPA 折中方案）
        response.headers["Content-Security-Policy"] = (
            f"default-src 'self'; script-src 'self' 'nonce-{nonce}'; "
            "connect-src 'self' https://aureon-production-659a.up.railway.app; "
            "img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; "
            "font-src 'self' https://fonts.gstatic.com; "
            "frame-ancestors 'none'; base-uri 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


# ── /metrics optional auth (S9) ──
_METRICS_KEY = os.environ.get("METRICS_KEY", "")

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

app = FastAPI(
    title="Aureon API",
    version=os.environ.get("BUILD_VERSION", "0.1.0"),
    lifespan=lifespan,
)

# ── Custom ThreadPoolExecutor for async routes ──
executor = ThreadPoolExecutor(max_workers=64)
app.state.executor = executor

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
app.add_middleware(SecurityHeadersMiddleware)

# ── /metrics optional auth (S9: protect /metrics with X-Metrics-Key header) ──
if _METRICS_KEY:
    @app.middleware("http")
    async def metrics_auth(request: Request, call_next):
        if request.url.path == "/metrics":
            key = request.headers.get("X-Metrics-Key", "")
            if key != _METRICS_KEY:
                return JSONResponse(status_code=403, content={"error": "forbidden", "detail": "Invalid or missing X-Metrics-Key"})
        return await call_next(request)

# ── Prometheus metrics ──
Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
).instrument(
    app,  # type: ignore[arg-type]
    latency_highr_buckets=[
        0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0,
    ],
).expose(app, endpoint="/metrics")  # type: ignore[arg-type]


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


# ── API 版本兼容中间件 (M8) ──
# 将旧版 /api/ 请求内部重写为 /api/v1/，保持向后兼容。
# 使用内部重写（而非 307 重定向）以避免：
# 1. httpx 等客户端默认不跟随重定向导致测试失败
# 2. POST 请求 body 在重定向中丢失
# 3. 额外的网络往返延迟
# 注意：此中间件在 logging_middleware 之前添加（更内层），
# 这样 logging_middleware 看到的是原始路径，API key 认证逻辑正常工作。
async def api_version_compat(request: Request, call_next):
    """将旧版 /api/ 请求内部重写为 /api/v1/。

    例外：/api/health 不需要版本化。
    """
    path = request.url.path
    if (
        path.startswith("/api/")
        and not path.startswith("/api/v1/")
        and not path.startswith("/api/health")
    ):
        # 内部重写 URL，不返回重定向
        new_path = "/api/v1/" + path[5:]
        request.scope["path"] = new_path
        request.scope["raw_path"] = new_path.encode()
    return await call_next(request)


app.middleware("http")(api_version_compat)


# ── Logging middleware (extracted to app.middleware.logging) ──
app.middleware("http")(logging_middleware)


class LangGraphRunRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)
    session_id: str = Field(default="", max_length=100)


@app.post("/api/v1/langgraph/run")
@limiter.limit("5/minute")
async def langgraph_run(req: LangGraphRunRequest, request: Request, user: dict = Depends(require_role(UserRole.VIEWER))):
    """Run LangGraph workflow for complex tasks."""
    from app.langgraph.graph import run_workflow
    result = await run_workflow(req.query, session_id=req.session_id)  # type: ignore[arg-type]
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
app.include_router(chat_router.router, prefix="/api/v1/chat", tags=["chat"])
app.include_router(rag_router.router, prefix="/api/v1/rag", tags=["rag"])
app.include_router(crew_router.router, prefix="/api/v1/crew", tags=["crew"])
app.include_router(stats_router)
app.include_router(analytics_router)
app.include_router(cost_router)
app.include_router(feature_flags_router)
app.include_router(observability_router, prefix="/api/v1/observability")
app.include_router(security_router, prefix="/api/v1/security")
app.include_router(audit_router, prefix="/api/v1/audit")
app.include_router(websocket_chat_router, tags=["websocket"])
app.include_router(ws_dashboard_router, tags=["websocket"])
app.include_router(users_router)
app.include_router(roles_router)
app.include_router(support_router)

app.include_router(reliability_router)

# ── SPA 静态文件（必须在 API 路由之后） ──
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    logger.warning("Static directory not found", path=os.path.abspath(static_dir))
