# -*- coding: utf-8 -*-
"""
Audit logging system for Aureon.
Records all write operations for compliance and traceability.
"""

import sqlite3

import structlog

from app.memory.db import get_db

logger = structlog.get_logger(__name__)


def init_audit_tables():
    """Create audit_logs table (append-only, immutable by design).

    The table enforces append-only semantics:
    - No UPDATE or DELETE triggers are created.
    - Application code should never issue DELETE/UPDATE on this table.
    """
    conn: sqlite3.Connection = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL DEFAULT 'default',
            user_id TEXT NOT NULL DEFAULT 'anonymous',
            action TEXT NOT NULL,
            resource_type TEXT NOT NULL DEFAULT '',
            resource_id TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            ip_address TEXT NOT NULL DEFAULT '',
            request_id TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_tenant_id
        ON audit_logs(tenant_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_created_at
        ON audit_logs(created_at)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_action
        ON audit_logs(action)
    """)
    conn.commit()
    logger.info("audit_tables_initialized")
