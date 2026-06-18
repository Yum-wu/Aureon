"""Tenant context middleware - extracts tenant_id from request.

Uses contextvars for async-safe storage of tenant context.
Supports tenant_id extraction from verified JWT claims only.

Security: JWT signature is verified before extracting tenant_id.
X-Tenant-ID header is NOT trusted (removable only by internal gateway).
"""

from contextvars import ContextVar
from typing import Optional

import structlog
from starlette.types import ASGIApp, Receive, Scope, Send

logger = structlog.get_logger(__name__)

# Context variable for storing current tenant ID (async-safe)
_tenant_id_var: ContextVar[str] = ContextVar("tenant_id", default="default")


class TenantContext:
    """Thread-safe and async-safe tenant context management."""

    @staticmethod
    def get_current_tenant_id() -> str:
        """Get the current tenant ID from context."""
        return _tenant_id_var.get("default")

    @staticmethod
    def set_tenant_id(tenant_id: str) -> None:
        """Set the current tenant ID in context."""
        _tenant_id_var.set(tenant_id)

    @staticmethod
    def clear() -> None:
        """Clear the current tenant context."""
        _tenant_id_var.set("default")


def get_current_tenant_id() -> str:
    """Get the current tenant ID from context."""
    return TenantContext.get_current_tenant_id()


def _extract_tenant_from_jwt_verified(token: str) -> Optional[str]:
    """Extract tenant_id from JWT token WITH signature verification.

    Uses rbac.verify_token() to validate signature, expiration, and algorithm.
    Returns None if token is invalid or tenant_id claim is missing.
    """
    try:
        from app.security.rbac import verify_token

        payload = verify_token(token)
        return payload.get("tenant_id")
    except Exception as e:
        logger.debug("tenant.jwt_verification_failed", error=str(e))
        return None


class TenantMiddleware:
    """Pure ASGI middleware for tenant isolation.

    Extracts tenant_id from verified JWT claims and stores in contextvars.

    Security model:
    - Only JWT claims (verified via rbac.verify_token) are trusted
    - X-Tenant-ID header is NOT used (client-forgeable)
    - Default tenant "default" is used when no valid JWT is present

    Why pure ASGI instead of BaseHTTPMiddleware:
    - BaseHTTPMiddleware buffers StreamingResponse (breaks SSE/TTFT)
    - BaseHTTPMiddleware disrupts contextvars propagation (Starlette limitation)
    - Pure ASGI has zero overhead and correct ContextVar handling
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        tenant_id = self._extract_tenant(scope)
        token = _tenant_id_var.set(tenant_id)

        try:
            await self.app(scope, receive, send)
        finally:
            _tenant_id_var.reset(token)

    @staticmethod
    def _extract_tenant(scope: Scope) -> str:
        """Extract tenant_id from ASGI scope (JWT only)."""
        headers = dict(scope.get("headers", []))

        # Extract tenant_id from verified JWT only
        auth = headers.get(b"authorization", b"").decode("latin-1")
        if auth.startswith("Bearer "):
            jwt_tenant = _extract_tenant_from_jwt_verified(auth[7:])
            if jwt_tenant:
                # Validate against allowlist if configured
                from app.config import settings

                if settings.tenant_allowlist:
                    allowed = {
                        t.strip()
                        for t in settings.tenant_allowlist.split(",")
                        if t.strip()
                    }
                    if allowed and jwt_tenant not in allowed:
                        logger.warning(
                            "tenant.jwt_tenant_not_in_allowlist",
                            tenant_id=jwt_tenant,
                            path=scope.get("path", ""),
                        )
                        return "default"
                return jwt_tenant

        return "default"
