"""Tests for app.audit — compliance log decorator, service, and router.

The audit module is part of the Phase 4 (enterprise governance) push and is
heavily relied on for compliance traces. These tests pin down:

- The Pydantic AuditLog model contract (required fields, defaults).
- The audit_action decorator: extracts request context (IP, user, request_id,
  X-Forwarded-For), captures resource_id from kwargs or return dict, builds
  metadata from remaining kwargs, and never breaks the wrapped route on
  failures.
- The record_audit service: persists to SQLite, tolerates insert failures.
- The get_audit_logs / get_audit_stats queries: tenant isolation, pagination,
  action/resource_type aggregations, recent counts.
- The HTTP router endpoints (read-only) using the FastAPI TestClient.
"""

import asyncio
import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def audit_db(tmp_path, monkeypatch):
    """Create an isolated SQLite database with the audit_logs schema.

    The audit module writes to ``app.memory.db.get_db()`` which is a singleton
    thread-local connection. We point DB_PATH at a tmp_path file and re-init
    the audit tables so each test gets a clean slate without touching the
    developer machine's real audit database.
    """
    db_file = tmp_path / "audit_test.db"
    monkeypatch.setattr("app.memory.db.DB_PATH", db_file)
    # Drop any cached thread-local connection so get_db() rebuilds against
    # the new path on the current test thread.
    monkeypatch.setattr("app.memory.db._thread_local", threading.local())
    # Best-effort cleanup of any other threads (best effort, pytest is
    # single-threaded by default).
    from app.audit import init_audit_tables
    init_audit_tables()
    yield db_file


@pytest.fixture
def client(audit_db):
    """TestClient bound to a minimal FastAPI app exposing the audit router."""
    from app.audit.router import router as audit_router

    app = FastAPI()
    app.include_router(audit_router)
    with TestClient(app) as c:
        yield c


def _make_request(*, headers=None, client_host="127.0.0.1", query_params=None):
    """Build a minimal stand-in for a FastAPI Request object.

    Only the attributes used by ``_build_audit_log`` are populated.
    """
    return SimpleNamespace(
        headers=headers or {},
        client=SimpleNamespace(host=client_host),
        query_params=query_params or {},
        state=SimpleNamespace(),
    )


# ── Pydantic model ──────────────────────────────────────────────────────────


class TestAuditLogModel:
    def test_required_fields(self):
        log = AuditLog = _import_audit_log()
        entry = AuditLog(action="upload", resource_type="document")
        assert entry.action == "upload"
        assert entry.resource_type == "document"
        assert entry.tenant_id == "default"
        assert entry.user_id == "anonymous"
        assert entry.resource_id == ""
        assert entry.metadata_json == "{}"
        assert entry.ip_address == ""
        assert entry.request_id == ""

    def test_overrides(self):
        AuditLog = _import_audit_log()
        entry = AuditLog(
            action="delete",
            resource_type="document",
            tenant_id="acme",
            user_id="u-42",
            resource_id="doc-1",
            metadata_json='{"k":"v"}',
            ip_address="10.0.0.1",
            request_id="req-1",
        )
        assert entry.tenant_id == "acme"
        assert entry.user_id == "u-42"
        assert entry.resource_id == "doc-1"
        assert entry.metadata_json == '{"k":"v"}'
        assert entry.ip_address == "10.0.0.1"
        assert entry.request_id == "req-1"


def _import_audit_log():
    from app.audit.models import AuditLog
    return AuditLog


# ── audit_action decorator ──────────────────────────────────────────────────


class TestAuditActionDecorator:
    def test_extracts_request_context_and_metadata(self, audit_db):
        from app.audit.decorator import _build_audit_log
        from app.audit.models import AuditLog

        request = _make_request(
            headers={"x-forwarded-for": "203.0.113.5, 10.0.0.1"},
            query_params={"user_id": "alice"},
        )
        request.state.request_id = "rid-123"

        log = _build_audit_log(
            action="upload",
            resource_type="document",
            resource_id_param=None,
            kwargs={
                "request": request,
                "filename": "report.pdf",
                "category": "finance",
            },
            result={"resource_id": "doc-999", "status": "ok"},
        )

        assert isinstance(log, AuditLog)
        assert log.action == "upload"
        assert log.resource_type == "document"
        assert log.resource_id == "doc-999"  # pulled from result dict
        assert log.ip_address == "203.0.113.5"  # first X-Forwarded-For hop
        assert log.request_id == "rid-123"
        assert log.user_id == "alice"
        meta = json.loads(log.metadata_json)
        assert meta["filename"] == "report.pdf"
        assert meta["category"] == "finance"
        # Sensitive keys must never leak into metadata.
        assert "request" not in meta
        assert "file" not in meta

    def test_resource_id_from_explicit_kwarg(self, audit_db):
        from app.audit.decorator import _build_audit_log

        request = _make_request()
        log = _build_audit_log(
            action="delete",
            resource_type="document",
            resource_id_param="doc_id",
            kwargs={"request": request, "doc_id": "abc-123"},
            result=None,
        )
        assert log.resource_id == "abc-123"

    def test_request_object_present_but_no_state_request_id(self, audit_db):
        """request_id must be empty string (not None) when absent."""
        from app.audit.decorator import _build_audit_log

        request = _make_request()  # no request_id on state
        log = _build_audit_log(
            action="query",
            resource_type="rag",
            resource_id_param=None,
            kwargs={"request": request},
            result={"answer": "42"},
        )
        assert log.request_id == ""
        # No resource_id and result is a dict but lacks resource_id/id
        assert log.resource_id == ""

    def test_falls_back_to_client_host_when_no_proxy_header(self, audit_db):
        from app.audit.decorator import _build_audit_log

        request = _make_request(client_host="192.168.1.10")
        log = _build_audit_log(
            action="login",
            resource_type="session",
            resource_id_param=None,
            kwargs={"request": request},
            result={},
        )
        assert log.ip_address == "192.168.1.10"

    def test_anonymous_user_when_request_missing(self, audit_db):
        from app.audit.decorator import _build_audit_log

        log = _build_audit_log(
            action="noop",
            resource_type="system",
            resource_id_param=None,
            kwargs={},
            result=None,
        )
        assert log.user_id == "anonymous"
        assert log.ip_address == ""
        assert log.resource_id == ""

    def test_metadata_truncates_non_json_serializable_values(self, audit_db):
        from app.audit.decorator import _build_audit_log

        class Opaque:
            def __repr__(self):
                return "<opaque>"

        log = _build_audit_log(
            action="update",
            resource_type="config",
            resource_id_param=None,
            kwargs={"request": _make_request(), "blob": Opaque()},
            result=None,
        )
        meta = json.loads(log.metadata_json)
        # The non-serializable value falls back to a truncated repr.
        assert isinstance(meta["blob"], str)
        assert len(meta["blob"]) <= 200

    async def test_decorator_runs_and_returns_handler_result(self, audit_db):
        """The decorator must await the original handler and return its value
        even if the audit log path itself fails."""
        from app.audit.decorator import audit_action

        @audit_action("create", "document")
        async def handler(**kwargs):
            return {"resource_id": "doc-1", "ok": True}

        result = await handler(request=_make_request(), name="x")
        assert result == {"resource_id": "doc-1", "ok": True}

    async def test_decorator_swallows_record_audit_failure(self, audit_db):
        """If record_audit raises, the request still succeeds (audit must
        never break the request path)."""
        from app.audit.decorator import audit_action

        with patch("app.audit.decorator.record_audit",
                   side_effect=RuntimeError("boom")):
            @audit_action("create", "document")
            async def handler(**kwargs):
                return {"resource_id": "doc-2"}

            result = await handler(request=_make_request())
        assert result == {"resource_id": "doc-2"}


# ── record_audit service ────────────────────────────────────────────────────


class TestRecordAuditService:
    async def test_writes_row(self, audit_db):
        from app.audit.service import record_audit, _insert_audit
        from app.audit.models import AuditLog

        log = AuditLog(
            action="upload",
            resource_type="document",
            resource_id="doc-1",
            tenant_id="t-1",
            user_id="alice",
            metadata_json='{"size": 12}',
        )
        await record_audit(log)

        conn = sqlite3.connect(str(audit_db))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT action, resource_type, resource_id, tenant_id, user_id, metadata_json "
            "FROM audit_logs WHERE tenant_id = 't-1'"
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        row = rows[0]
        assert row["action"] == "upload"
        assert row["resource_type"] == "document"
        assert row["resource_id"] == "doc-1"
        assert row["user_id"] == "alice"
        assert json.loads(row["metadata_json"]) == {"size": 12}

    async def test_failure_does_not_raise(self, audit_db):
        from app.audit.service import record_audit
        from app.audit.models import AuditLog

        # Force the synchronous insert to raise; the async wrapper must
        # swallow it and log a warning.
        with patch("app.audit.service._insert_audit",
                   side_effect=RuntimeError("db down")):
            log = AuditLog(action="x", resource_type="y")
            await record_audit(log)  # should not raise

    def test_insert_audit_uses_thread_local_connection(self, audit_db):
        """Sanity check that _insert_audit runs synchronously against the
        thread-local connection (called via asyncio.to_thread)."""
        from app.audit.service import _insert_audit
        from app.audit.models import AuditLog

        log = AuditLog(
            action="sync", resource_type="test", tenant_id="t-sync",
        )
        _insert_audit(log)

        conn = sqlite3.connect(str(audit_db))
        cnt = conn.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE tenant_id='t-sync'"
        ).fetchone()[0]
        conn.close()
        assert cnt == 1


# ── Query / aggregation ────────────────────────────────────────────────────


class TestAuditQueries:
    def _insert(self, audit_db, *, action, resource_type, tenant_id="default",
                resource_id="", created_at=None):
        from app.audit.service import _insert_audit
        from app.audit.models import AuditLog
        log = AuditLog(
            action=action,
            resource_type=resource_type,
            tenant_id=tenant_id,
            resource_id=resource_id,
        )
        if created_at is not None:
            # Use a sentinel marker so we can override the timestamp after
            # the fact via a direct UPDATE — the _insert_audit path always
            # writes the current UTC time.
            pass
        _insert_audit(log)
        if created_at is not None:
            conn = sqlite3.connect(str(audit_db))
            conn.execute(
                "UPDATE audit_logs SET created_at = ? WHERE id = (SELECT MAX(id) FROM audit_logs)",
                (created_at,),
            )
            conn.commit()
            conn.close()

    def test_get_audit_logs_paginates_and_isolates_tenant(self, audit_db):
        from app.audit.service import get_audit_logs

        for i in range(5):
            self._insert(audit_db, action="upload", resource_type="document",
                         tenant_id="acme", resource_id=f"d-{i}")
        for i in range(3):
            self._insert(audit_db, action="delete", resource_type="document",
                         tenant_id="globex", resource_id=f"g-{i}")

        page1 = get_audit_logs(tenant_id="acme", limit=2, offset=0)
        assert page1.total == 5
        assert len(page1.logs) == 2
        # Most-recent first
        assert page1.logs[0].resource_id == "d-4"
        assert page1.logs[1].resource_id == "d-3"

        page3 = get_audit_logs(tenant_id="acme", limit=2, offset=4)
        assert len(page3.logs) == 1
        assert page3.logs[0].resource_id == "d-0"

        # Tenant isolation
        other = get_audit_logs(tenant_id="globex", limit=50, offset=0)
        assert other.total == 3
        assert all(log.tenant_id == "globex" for log in other.logs)

    def test_get_audit_stats_aggregates(self, audit_db):
        from app.audit.service import get_audit_stats

        for i in range(4):
            self._insert(audit_db, action="upload", resource_type="document",
                         tenant_id="acme")
        for i in range(2):
            self._insert(audit_db, action="delete", resource_type="document",
                         tenant_id="acme")
        for i in range(1):
            self._insert(audit_db, action="index", resource_type="index",
                         tenant_id="acme")

        stats = get_audit_stats(tenant_id="acme")
        assert stats.total_logs == 7
        assert stats.actions == {"upload": 4, "delete": 2, "index": 1}
        assert stats.resource_types == {"document": 6, "index": 1}

    def test_recent_counts_windowed_correctly(self, audit_db):
        """Stats must only count rows inside the 1h/24h windows."""
        from app.audit.service import get_audit_stats

        now = datetime.now(timezone.utc)
        recent = (now - timedelta(minutes=5)).isoformat()
        old = (now - timedelta(hours=48)).isoformat()

        # 2 recent, 1 old
        self._insert(audit_db, action="upload", resource_type="document",
                     tenant_id="acme", created_at=recent)
        self._insert(audit_db, action="upload", resource_type="document",
                     tenant_id="acme", created_at=recent)
        self._insert(audit_db, action="upload", resource_type="document",
                     tenant_id="acme", created_at=old)

        stats = get_audit_stats(tenant_id="acme")
        assert stats.total_logs == 3
        assert stats.recent_count_1h == 2
        assert stats.recent_count_24h == 2  # 48h-old rows excluded


# ── HTTP router endpoints ──────────────────────────────────────────────────


class TestAuditRouter:
    def test_list_logs_returns_paginated_payload(self, audit_db, client):
        from app.audit.service import _insert_audit
        from app.audit.models import AuditLog

        for i in range(3):
            _insert_audit(AuditLog(action="upload", resource_type="document",
                                    tenant_id="acme", resource_id=f"d-{i}"))

        resp = client.get("/logs", params={"tenant_id": "acme", "limit": 2, "offset": 0})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert len(body["logs"]) == 2
        assert body["limit"] == 2
        assert body["offset"] == 0

    def test_stats_endpoint_aggregates(self, audit_db, client):
        from app.audit.service import _insert_audit
        from app.audit.models import AuditLog

        _insert_audit(AuditLog(action="upload", resource_type="document",
                                tenant_id="acme"))
        _insert_audit(AuditLog(action="upload", resource_type="document",
                                tenant_id="acme"))
        _insert_audit(AuditLog(action="index", resource_type="index",
                                tenant_id="acme"))

        resp = client.get("/stats", params={"tenant_id": "acme"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_logs"] == 3
        assert body["actions"] == {"upload": 2, "index": 1}
        assert body["resource_types"] == {"document": 2, "index": 1}

    def test_list_logs_validates_pagination_bounds(self, audit_db, client):
        # limit=0 is rejected by FastAPI Query(ge=1)
        resp = client.get("/logs", params={"limit": 0})
        assert resp.status_code == 422
        # limit > 500 is rejected
        resp = client.get("/logs", params={"limit": 1000})
        assert resp.status_code == 422
        # negative offset is rejected
        resp = client.get("/logs", params={"offset": -1})
        assert resp.status_code == 422
