# -*- coding: utf-8 -*-
"""Audit decorator - auto-log API operations.

Usage:
    @router.post("/api/rag/upload")
    @audit_action("upload", "document")
    async def upload_endpoint(...):
        ...

The decorator inspects the function signature to find a ``request: Request``
parameter. From it, user_id, IP, and request_id are extracted automatically.
"""

from __future__ import annotations

import json
import functools
from typing import Any, Callable, Coroutine, Optional

import structlog

from app.audit.models import AuditLog
from app.audit.service import record_audit

logger = structlog.get_logger(__name__)


def audit_action(
    action: str,
    resource_type: str,
    resource_id_param: Optional[str] = None,
) -> Callable[
    [Callable[..., Coroutine[Any, Any, Any]]],
    Callable[..., Coroutine[Any, Any, Any]],
]:
    """Decorator that records an audit log entry after a successful route call.

    Args:
        action: Audit action name (e.g. "upload", "index", "query", "create").
        resource_type: Resource type (e.g. "document", "index", "session").
        resource_id_param: Optional name of a keyword argument whose value
            should be stored as ``resource_id``. If ``None``, the decorator
            tries to extract ``resource_id`` from the return dict.
    """

    def decorator(fn: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Coroutine[Any, Any, Any]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Execute the original handler first
            result = await fn(*args, **kwargs)

            # Fire-and-forget audit record
            try:
                log = _build_audit_log(
                    action=action,
                    resource_type=resource_type,
                    resource_id_param=resource_id_param,
                    kwargs=kwargs,
                    result=result,
                )
                await record_audit(log)
            except Exception as exc:
                logger.warning(
                    "audit_decorator_failed",
                    action=action,
                    resource_type=resource_type,
                    error=str(exc),
                )

            return result

        return wrapper

    return decorator


def _build_audit_log(
    *,
    action: str,
    resource_type: str,
    resource_id_param: Optional[str],
    kwargs: dict[str, Any],
    result: Any,
) -> AuditLog:
    """Extract request context and build an AuditLog."""
    request = kwargs.get("request")

    user_id = "anonymous"
    ip_address = ""
    request_id = ""

    if request is not None:
        # Extract client IP (supports X-Forwarded-For behind proxy)
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ip_address = forwarded.split(",")[0].strip()
        elif request.client:
            ip_address = request.client.host

        # Request ID injected by logging_middleware
        request_id = getattr(request.state, "request_id", "") or ""
        if not request_id:
            # Fallback: try structlog contextvars
            try:
                import structlog.contextvars
                ctx = structlog.contextvars.get_contextvars()
                request_id = ctx.get("request_id", "")
            except Exception:
                pass

        # User ID from headers or query params (extensible)
        user_id = (
            request.headers.get("x-user-id")
            or request.query_params.get("user_id", "anonymous")
        )

    # Determine resource_id
    resource_id = ""
    if resource_id_param and resource_id_param in kwargs:
        resource_id = str(kwargs[resource_id_param])
    elif isinstance(result, dict):
        resource_id = str(result.get("resource_id", result.get("id", "")))

    # Build metadata from remaining kwargs (excluding large objects)
    metadata: dict[str, Any] = {}
    for key, value in kwargs.items():
        if key in ("request", "file", "content"):
            continue
        if value is not None and not callable(value):
            try:
                json.dumps(value)
                metadata[key] = value
            except (TypeError, ValueError):
                metadata[key] = str(value)[:200]

    return AuditLog(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_json=json.dumps(metadata, ensure_ascii=False, default=str),
        ip_address=ip_address,
        request_id=request_id,
        user_id=user_id,
    )
