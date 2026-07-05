# -*- coding: utf-8 -*-
"""Audit logging service — async write + query via PostgreSQL asyncpg."""

from datetime import datetime, timezone, timedelta

import structlog

from app.audit.models import (
    AuditLog,
    AuditLogResponse,
    AuditStatsResponse,
    AuditLogsResponse,
)

logger = structlog.get_logger(__name__)


async def _get_pool():
    from app.database.connection import get_db_pool
    pool = get_db_pool()
    if pool is None:
        raise RuntimeError("DATABASE_URL not configured — cannot access audit logs")
    return pool


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

async def record_audit(log: AuditLog) -> None:
    """Persist an audit log entry (non-blocking)."""
    try:
        pool = await _get_pool()
        now = datetime.now(timezone.utc)
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO audit_logs
                    (tenant_id, user_id, action, resource_type, resource_id,
                     metadata_json, ip_address, request_id, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                log.tenant_id,
                log.user_id,
                log.action,
                log.resource_type,
                log.resource_id,
                log.metadata_json,
                log.ip_address,
                log.request_id,
                now,
            )
        logger.info(
            "audit_recorded",
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            user_id=log.user_id,
        )
    except Exception as exc:
        # Audit failures must never break the request path
        logger.warning("audit_record_failed", error=str(exc), action=log.action)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def _row_to_response(row) -> AuditLogResponse:
    """Convert an asyncpg Record to an AuditLogResponse model."""
    created_at = row["created_at"]
    if hasattr(created_at, "isoformat"):
        created_at = created_at.isoformat()

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
        created_at=created_at,
    )


async def get_audit_logs(
    tenant_id: str = "default",
    limit: int = 50,
    offset: int = 0,
) -> AuditLogsResponse:
    """Query audit logs for a tenant with pagination."""
    pool = await _get_pool()

    async with pool.acquire() as conn:
        total_row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM audit_logs WHERE tenant_id = $1",
            tenant_id,
        )
        total: int = total_row["cnt"] if total_row else 0

        rows = await conn.fetch(
            """
            SELECT id, tenant_id, user_id, action, resource_type, resource_id,
                   metadata_json, ip_address, request_id, created_at
            FROM audit_logs
            WHERE tenant_id = $1
            ORDER BY id DESC
            LIMIT $2 OFFSET $3
            """,
            tenant_id, limit, offset,
        )

    logs = [_row_to_response(r) for r in rows]
    return AuditLogsResponse(logs=logs, total=total, limit=limit, offset=offset)


async def get_audit_stats(
    tenant_id: str = "default",
    now: datetime | None = None,
) -> AuditStatsResponse:
    """Aggregate audit statistics for a tenant."""
    pool = await _get_pool()

    async with pool.acquire() as conn:
        total_row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM audit_logs WHERE tenant_id = $1",
            tenant_id,
        )
        total_logs: int = total_row["cnt"] if total_row else 0

        # Action breakdown
        action_rows = await conn.fetch(
            "SELECT action, COUNT(*) AS cnt FROM audit_logs WHERE tenant_id = $1 GROUP BY action",
            tenant_id,
        )
        actions = {row["action"]: row["cnt"] for row in action_rows}

        # Resource type breakdown
        rt_rows = await conn.fetch(
            "SELECT resource_type, COUNT(*) AS cnt FROM audit_logs WHERE tenant_id = $1 GROUP BY resource_type",
            tenant_id,
        )
        resource_types = {row["resource_type"]: row["cnt"] for row in rt_rows}

        # Recent counts
        now = now or datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)
        one_day_ago = now - timedelta(hours=24)

        recent_1h_row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM audit_logs WHERE tenant_id = $1 AND created_at >= $2",
            tenant_id, one_hour_ago,
        )
        recent_count_1h: int = recent_1h_row["cnt"] if recent_1h_row else 0

        recent_24h_row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM audit_logs WHERE tenant_id = $1 AND created_at >= $2",
            tenant_id, one_day_ago,
        )
        recent_count_24h: int = recent_24h_row["cnt"] if recent_24h_row else 0

    return AuditStatsResponse(
        total_logs=total_logs,
        actions=actions,
        resource_types=resource_types,
        recent_count_1h=recent_count_1h,
        recent_count_24h=recent_count_24h,
    )
