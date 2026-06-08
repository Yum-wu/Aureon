# -*- coding: utf-8 -*-
"""Pydantic models for the audit logging system."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AuditLog(BaseModel):
    """Single audit log entry.

    Attributes:
        id: Auto-incremented primary key.
        tenant_id: Multi-tenant isolation key.
        user_id: Identity of the actor performing the action.
        action: The operation performed (create, update, delete, query, upload, index).
        resource_type: Type of resource acted upon (document, index, config, user, session).
        resource_id: Identifier of the specific resource.
        metadata_json: Additional context as JSON string.
        ip_address: Client IP address.
        request_id: Correlation ID for request tracing.
        created_at: Timestamp of the event.
    """

    id: Optional[int] = None
    tenant_id: str = "default"
    user_id: str = "anonymous"
    action: str = Field(..., description="Action: create, update, delete, query, upload, index")
    resource_type: str = Field(..., description="Resource type: document, index, config, user, session")
    resource_id: str = ""
    metadata_json: str = "{}"
    ip_address: str = ""
    request_id: str = ""
    created_at: Optional[datetime] = None


class AuditLogResponse(BaseModel):
    """Response wrapper for a single audit log."""

    id: int
    tenant_id: str
    user_id: str
    action: str
    resource_type: str
    resource_id: str
    metadata_json: str
    ip_address: str
    request_id: str
    created_at: str


class AuditStatsResponse(BaseModel):
    """Aggregated audit statistics."""

    total_logs: int = 0
    actions: dict[str, int] = {}
    resource_types: dict[str, int] = {}
    recent_count_1h: int = 0
    recent_count_24h: int = 0


class AuditLogsResponse(BaseModel):
    """Paginated list of audit logs."""

    logs: list[AuditLogResponse] = []
    total: int = 0
    limit: int = 50
    offset: int = 0
