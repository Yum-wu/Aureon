"""Tenant context middleware - extracts tenant_id from request.

Uses contextvars for async-safe storage of tenant context.
Supports multiple tenant_id extraction methods:
- X-Tenant-ID header (highest priority)
- JWT token tenant_id claim
- Default "default" tenant
"""

from contextvars import ContextVar
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


class TenantMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for tenant isolation.

    Extracts tenant_id from request and stores it in contextvars.
    Extraction priority:
    1. X-Tenant-ID header
    2. JWT token tenant_id claim
    3. Default "default" tenant
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        tenant_id = "default"  # Default tenant

        # 1. Try X-Tenant-ID header (highest priority)
        header_tenant = request.headers.get("X-Tenant-ID")
        if header_tenant:
            tenant_id = header_tenant
            logger.debug("Tenant ID from header: %s", tenant_id)

        # 2. Try JWT token tenant_id claim
        if tenant_id == "default":  # Only if not set from header
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]  # Remove "Bearer " prefix
                jwt_tenant = _extract_tenant_from_jwt(token)
                if jwt_tenant:
                    tenant_id = jwt_tenant
                    logger.debug("Tenant ID from JWT: %s", tenant_id)

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
