# -*- coding: utf-8 -*-
"""Audit logging service - async write + query for compliance traces.

Write path: SQLite append-only (async via asyncio.to_thread).
Read path:  Direct SQLite query (single-threaded, WAL mode).
"""

import asyncio
import sqlite3
from datetime import datetime, timezone, timedelta

import structlog

from app.audit.models import (
    AuditLog,
    AuditLogResponse,
    AuditStatsResponse,
    AuditLogsResponse,
)
from app.memory.db import get_db

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

async def record_audit(log: AuditLog) -> None:
    """Persist an audit log entry (fire-and-forget, non-blocking).

    Writes to SQLite audit_logs table. If PostgreSQL is configured in the
    future, write to both backends concurrently.
    """
    try:
        await asyncio.to_thread(_insert_audit, log)
    except Exception as exc:
        # Audit failures must never break the request path
        logger.warning("audit_record_failed", error=str(exc), action=log.action)


def _insert_audit(log: AuditLog) -> None:
    """Synchronous insert - called via asyncio.to_thread."""
    conn: sqlite3.Connection = get_db()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO audit_logs
            (tenant_id, user_id, action, resource_type, resource_id,
             metadata_json, ip_address, request_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            log.tenant_id,
            log.user_id,
            log.action,
            log.resource_type,
            log.resource_id,
            log.metadata_json,
            log.ip_address,
            log.request_id,
            now,
        ),
    )
    conn.commit()
    logger.info(
        "audit_recorded",
        action=log.action,
        resource_type=log.resource_type,
        resource_id=log.resource_id,
        user_id=log.user_id,
    )


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_audit_logs(
    tenant_id: str = "default",
    limit: int = 50,
    offset: int = 0,
) -> AuditLogsResponse:
    """Query audit logs for a tenant with pagination."""
    conn: sqlite3.Connection = get_db()

    total_row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM audit_logs WHERE tenant_id = ?",
        (tenant_id,),
    ).fetchone()
    total: int = total_row["cnt"] if total_row else 0

    rows = conn.execute(
        """
        SELECT id, tenant_id, user_id, action, resource_type, resource_id,
               metadata_json, ip_address, request_id, created_at
        FROM audit_logs
        WHERE tenant_id = ?
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        (tenant_id, limit, offset),
    ).fetchall()

    logs = [_row_to_response(r) for r in rows]
    return AuditLogsResponse(logs=logs, total=total, limit=limit, offset=offset)


def get_audit_stats(tenant_id: str = "default") -> AuditStatsResponse:
    """Aggregate audit statistics for a tenant."""
    conn: sqlite3.Connection = get_db()

    total_row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM audit_logs WHERE tenant_id = ?",
        (tenant_id,),
    ).fetchone()
    total_logs: int = total_row["cnt"] if total_row else 0

    # Action breakdown
    action_rows = conn.execute(
        "SELECT action, COUNT(*) AS cnt FROM audit_logs WHERE tenant_id = ? GROUP BY action",
        (tenant_id,),
    ).fetchall()
    actions = {row["action"]: row["cnt"] for row in action_rows}

    # Resource type breakdown
    rt_rows = conn.execute(
        "SELECT resource_type, COUNT(*) AS cnt FROM audit_logs WHERE tenant_id = ? GROUP BY resource_type",
        (tenant_id,),
    ).fetchall()
    resource_types = {row["resource_type"]: row["cnt"] for row in rt_rows}

    # Recent counts
    now = datetime.now(timezone.utc)
    one_hour_ago = (now - timedelta(hours=1)).isoformat()
    one_day_ago = (now - timedelta(hours=24)).isoformat()

    recent_1h_row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM audit_logs WHERE tenant_id = ? AND created_at >= ?",
        (tenant_id, one_hour_ago),
    ).fetchone()
    recent_count_1h: int = recent_1h_row["cnt"] if recent_1h_row else 0

    recent_24h_row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM audit_logs WHERE tenant_id = ? AND created_at >= ?",
        (tenant_id, one_day_ago),
    ).fetchone()
    recent_count_24h: int = recent_24h_row["cnt"] if recent_24h_row else 0

    return AuditStatsResponse(
        total_logs=total_logs,
        actions=actions,
        resource_types=resource_types,
        recent_count_1h=recent_count_1h,
        recent_count_24h=recent_count_24h,
    )


def _row_to_response(row: sqlite3.Row) -> AuditLogResponse:
    """Convert a sqlite3.Row to an AuditLogResponse model."""
    return AuditLogResponse(
        id=row["id"],
        tenant_id=row["tenant_id"],
        user_id=row["user_id"],
        action=row["action"],
        resource_type=row["resource_type"],
        resource_id=row["resource_id"],
        metadata_json=row["metadata_json"],
        ip_address=row["ip_address"],
        request_id=row["request_id"],
        created_at=row["created_at"],
    )
