"""Tenant context middleware - extracts tenant_id from request.

Uses contextvars for async-safe storage of tenant context.
Supports multiple tenant_id extraction methods:
- X-Tenant-ID header (highest priority)
- JWT token tenant_id claim
- Default "default" tenant
"""

from contextvars import ContextVar
import os
from typing import Optional

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = structlog.get_logger(__name__)

# Context variable for storing current tenant ID (async-safe)
_tenant_id_var: ContextVar[str] = ContextVar("tenant_id", default="default")


class TenantContext:
    """Thread-safe and async-safe tenant context management."""

    @staticmethod
    def get_current_tenant_id() -> str:
        """Get the current tenant ID from context.

        Returns:
            Current tenant ID, defaults to "default"
        """
        return _tenant_id_var.get("default")

    @staticmethod
    def set_tenant_id(tenant_id: str) -> None:
        """Set the current tenant ID in context.

        Args:
            tenant_id: The tenant ID to set
        """
        _tenant_id_var.set(tenant_id)

    @staticmethod
    def clear() -> None:
        """Clear the current tenant context."""
        _tenant_id_var.set("default")


def get_current_tenant_id() -> str:
    """Get the current tenant ID from context.

    This is a convenience function that wraps TenantContext.get_current_tenant_id().

    Returns:
        Current tenant ID, defaults to "default"
    """
    return TenantContext.get_current_tenant_id()


def _extract_tenant_from_jwt(token: str) -> Optional[str]:
    """Extract tenant_id from JWT token without validation.

    This is a lightweight extraction that doesn't verify the token signature.
    Token validation should be handled separately if needed.

    Args:
        token: JWT token string

    Returns:
        tenant_id if found, None otherwise
    """
    try:
        import base64
        import json

        # Split JWT parts
        parts = token.split(".")
        if len(parts) != 3:
            return None

        # Decode payload (second part)
        payload = parts[1]
        # Add padding if needed
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding

        # Decode base64
        decoded = base64.urlsafe_b64decode(payload)
        payload_data = json.loads(decoded)

        # Extract tenant_id
        return payload_data.get("tenant_id")
    except Exception as e:
        logger.debug("Failed to extract tenant from JWT: %s", e)
        return None


def _extract_verified_tenant_from_jwt(token: str) -> Optional[str]:
    """Extract tenant_id from a JWT *with signature verification*.

    Falls back to None on any verification error (expired, bad signature,
    malformed).  Never accepts an unverified claim.
    """
    try:
        from app.security import verify_token
        payload = verify_token(token)
    except Exception as e:
        logger.debug("JWT verification failed: %s", e)
        return None
    return payload.get("tenant_id")


def _resolve_api_key_tenant(request: Request) -> Optional[str]:
    """Map an API key to a tenant id.

    The mapping is read from the ``API_KEY_TENANT_MAP`` environment variable
    formatted as ``"<key>:<tenant>;<key>:<tenant>"``.  When ``API_AUTH_KEY``
    is set but no mapping exists, all callers share the ``default`` tenant
    (single-tenant mode).
    """
    from app.config import settings

    api_key = request.headers.get("X-API-Key")
    if not api_key or not settings.api_auth_key:
        return None
    if api_key != settings.api_auth_key:
        # Invalid key — do not leak which tenant is associated.
        return None

    raw = os.environ.get("API_KEY_TENANT_MAP", "")
    if not raw:
        return "default"
    try:
        for entry in raw.split(";"):
            if not entry.strip():
                continue
            k, _, tenant = entry.partition(":")
            if k == api_key and tenant:
                return tenant.strip()
    except Exception as e:
        logger.debug("Failed to parse API_KEY_TENANT_MAP: %s", e)
    return "default"


async def _resolve_principal_tenant(request: Request) -> Optional[str]:
    """Resolve the authenticated principal's tenant from the request.

    Priority:
    1. Verified JWT ``tenant_id`` claim.
    2. API-key-to-tenant mapping (when ``X-API-Key`` is provided).

    Returns None when the caller is unauthenticated.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        tenant = _extract_verified_tenant_from_jwt(token)
        if tenant:
            return tenant

    return _resolve_api_key_tenant(request)


class TenantMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for tenant isolation.

    Extracts tenant_id from request and stores it in contextvars.
    Extraction priority:
    1. X-Tenant-ID header (only trusted when an authenticated principal
       agrees with the value — see `_verify_tenant_header`)
    2. JWT token tenant_id claim (verified)
    3. API-key-to-tenant mapping (when API_AUTH_KEY is configured)
    4. Default "default" tenant
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        tenant_id = "default"  # Default tenant

        # 1. Try X-Tenant-ID header, but only trust it if it matches an
        # authenticated principal (JWT claim or API-key mapping).
        header_tenant = request.headers.get("X-Tenant-ID")
        if header_tenant:
            principal_tenant = await _resolve_principal_tenant(request)
            if principal_tenant is None:
                # No authenticated principal — reject header-based claim.
                logger.warning("Rejected X-Tenant-ID without authenticated principal")
            elif header_tenant == principal_tenant:
                tenant_id = header_tenant
                logger.debug("Tenant ID from header (verified): %s", tenant_id)
            else:
                # Header disagrees with authenticated principal — spoofing attempt.
                logger.warning(
                    "Tenant header mismatch: header=%s principal=%s",
                    header_tenant, principal_tenant,
                )
                return Response(
                    content='{"detail":"Tenant header does not match authenticated principal"}',
                    status_code=403,
                    media_type="application/json",
                )

        # 2. Try JWT token tenant_id claim (verified signature)
        if tenant_id == "default":  # Only if not set from header
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]  # Remove "Bearer " prefix
                jwt_tenant = _extract_verified_tenant_from_jwt(token)
                if jwt_tenant:
                    tenant_id = jwt_tenant
                    logger.debug("Tenant ID from verified JWT: %s", tenant_id)

        # 3. Try API-key-to-tenant mapping
        if tenant_id == "default":
            key_tenant = _resolve_api_key_tenant(request)
            if key_tenant:
                tenant_id = key_tenant
                logger.debug("Tenant ID from API key: %s", tenant_id)

        # Set tenant context
        TenantContext.set_tenant_id(tenant_id)

        # Add tenant_id to request state for easy access
        request.state.tenant_id = tenant_id

        try:
            response = await call_next(request)
            return response
        finally:
            # Clear tenant context after request completes
            TenantContext.clear()
