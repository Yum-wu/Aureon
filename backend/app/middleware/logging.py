"""HTTP logging middleware �� request ID injection, API key auth, security headers.

Extracted from main.py to separate middleware concerns from app creation.
"""

import hmac
import time
import uuid

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse

logger = structlog.get_logger()


async def logging_middleware(request: Request, call_next):
    """Inject request_id + security headers + optional auth, log request completion."""
    # 函数内导入 settings，确保 config 模块被 reload 后仍使用当前 settings
    from app.config import settings

    request_id = str(uuid.uuid4())[:8]
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    # API Key authentication (skip when API_AUTH_KEY is not configured)
    # SSO login + demo-token endpoints are public — skip API key check
    _skip_auth_paths = (
        "/api/security/sso/login",
        "/api/v1/security/sso/login",
        "/api/security/demo-token",
        "/api/v1/security/demo-token",
        "/api/health",
        "/health",
    )
    if settings.api_auth_key and request.url.path.startswith("/api/") and request.url.path not in _skip_auth_paths:
        # Public endpoints that don't require auth
        public_paths = {
            "/api/health",
            "/api/crew/health",
            "/metrics",
            "/api/security/sso/login",
            "/api/v1/security/sso/login",
            "/api/security/demo-token",
            "/api/v1/security/demo-token",
        }
        if request.url.path not in public_paths:
            # Skip API key check if a valid JWT Bearer token is present
            # (JWT validation is done by require_role at the endpoint level)
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer ") and len(auth_header) > 10:
                pass
            else:
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
