"""Tests for app.audit — security/compliance log system.

Covers the audit decorator (request-context extraction and fire-and-forget
write) and the read APIs (list + stats). The write path is exercised
end-to-end against a real SQLite table; the test relies on `init_db()`
+ `init_audit_tables()` running in the shared offloads/memory.db singleton,
matching the pattern used by test_memory.py and test_integration.py.
"""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


# ── decorator: log construction (pure, no I/O) ──


class TestBuildAuditLog:
    """Exercise _build_audit_log across all metadata-source branches.

    These cases are pure CPU work and run without any DB or HTTP server,
    so they are the most reliable regression coverage for the decorator.
    """

    def _call(self, **overrides):
        from app.audit.decorator import _build_audit_log
        kwargs = {"action": "upload", "resource_type": "document", "resource_id_param": None, "result": None, "kwargs": {}}
        kwargs.update(overrides)
        return _build_audit_log(**kwargs)

    def test_no_request_uses_anonymous_defaults(self):
        log = self._call(kwargs={}, result=None)
        assert log.user_id == "anonymous"
        assert log.ip_address == ""
        assert log.request_id == ""

    def test_request_extracts_forwarded_for_ip(self):
        """X-Forwarded-For must be parsed with the first hop selected."""
        request = SimpleNamespace(
            headers={"x-forwarded-for": "203.0.113.5, 10.0.0.1"},
            client=SimpleNamespace(host="127.0.0.1"),
            query_params={},
            state=SimpleNamespace(request_id="rid-123"),
        )
        log = self._call(kwargs={"request": request}, result=None)
        assert log.ip_address == "203.0.113.5"
        assert log.request_id == "rid-123"

    def test_request_falls_back_to_client_host_when_no_forwarded_header(self):
        request = SimpleNamespace(
            headers={},
            client=SimpleNamespace(host="198.51.100.7"),
            query_params={},
            state=SimpleNamespace(request_id="rid-2"),
        )
        log = self._call(kwargs={"request": request}, result=None)
        assert log.ip_address == "198.51.100.7"

    def test_user_id_from_jwt_or_anonymous(self):
        """user_id is now extracted from verified JWT only, not from forgeable headers."""
        request = SimpleNamespace(
            headers={"x-user-id": "alice"},
            client=None,
            query_params={"user_id": "bob"},
            state=SimpleNamespace(request_id=""),
        )
        log = self._call(kwargs={"request": request}, result=None)
        # x-user-id header is no longer trusted (security fix)
        assert log.user_id == "anonymous"

    def test_user_id_falls_back_to_anonymous(self):
        """Without a valid JWT, user_id defaults to 'anonymous'."""
        request = SimpleNamespace(
            headers={},
            client=None,
            query_params={"user_id": "carol"},
            state=SimpleNamespace(request_id=""),
        )
        log = self._call(kwargs={"request": request}, result=None)
        # query param user_id is no longer trusted (security fix)
        assert log.user_id == "anonymous"

    def test_resource_id_from_kwarg_param(self):
        log = self._call(
            resource_id_param="document_id",
            kwargs={"document_id": 42, "request": None},
            result=None,
        )
        assert log.resource_id == "42"

    def test_resource_id_from_result_dict_id_field(self):
        log = self._call(kwargs={}, result={"id": "doc-99"})
        assert log.resource_id == "doc-99"

    def test_resource_id_from_result_dict_resource_id_field(self):
        log = self._call(kwargs={}, result={"resource_id": "rid-from-result"})
        assert log.resource_id == "rid-from-result"

    def test_metadata_excludes_request_file_content(self):
        """request, file, content kwargs must never land in metadata_json."""
        sentinel = SimpleNamespace(
            headers={"x-user-id": "x"},
            client=None,
            query_params={},
            state=SimpleNamespace(request_id=""),
        )
        log = self._call(
            kwargs={"request": sentinel, "file": "binary", "content": "body", "page": 1, "kind": "doc"},
            result=None,
        )
        meta = json.loads(log.metadata_json)
        assert "request" not in meta
        assert "file" not in meta
        assert "content" not in meta
        assert meta["page"] == 1
        assert meta["kind"] == "doc"

    def test_metadata_sanitizes_unserializable_values(self):
        """Non-JSON values must be coerced to truncated strings, not raise."""
        class Opaque:
            def __repr__(self):
                return "<opaque>"

        log = self._call(
            kwargs={"weird": Opaque()},
            result=None,
        )
        meta = json.loads(log.metadata_json)
        # Fallback: str(value)[:200] per decorator's contract
        assert "weird" in meta
        assert isinstance(meta["weird"], str)


# ── decorator: wrapper behavior ──


class TestAuditDecorator:
    @pytest.mark.asyncio
    async def test_wrapper_calls_record_audit_after_handler(self):
        from app.audit.decorator import audit_action

        async def handler(*args, **kwargs):
            return {"id": "x1"}

        decorated = audit_action("create", "document")(handler)
        with patch("app.audit.decorator.record_audit", new=AsyncMock()) as mock_record:
            result = await decorated()
        assert result == {"id": "x1"}
        mock_record.assert_awaited_once()
        log = mock_record.await_args.args[0]
        assert log.action == "create"
        assert log.resource_type == "document"
        assert log.resource_id == "x1"

    @pytest.mark.asyncio
    async def test_wrapper_never_breaks_handler_on_audit_failure(self):
        """If record_audit raises, the original result must still be returned.

        Audit failures are logged but must not propagate — this is a
        compliance safety net, not a hard dependency.
        """
        from app.audit.decorator import audit_action

        async def handler(*args, **kwargs):
            return "ok"

        decorated = audit_action("query", "config")(handler)
        with patch(
            "app.audit.decorator.record_audit",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ):
            # Must not raise
            result = await decorated()
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_wrapper_returns_handler_result_even_when_audit_swallows_exception(self):
        """Audit log call returns the result unmodified."""
        from app.audit.decorator import audit_action

        async def handler(*args, **kwargs):
            return {"answer": 42}

        decorated = audit_action("query", "config")(handler)
        with patch("app.audit.decorator.record_audit", new=AsyncMock()):
            result = await decorated(kw1="v1")
        assert result == {"answer": 42}


# ── models: validation ──


class TestAuditLogModel:
    def test_minimal_required_fields(self):
        from app.audit.models import AuditLog
        log = AuditLog(action="create", resource_type="document")
        assert log.action == "create"
        assert log.resource_type == "document"
        # Sensible defaults
        assert log.tenant_id == "default"
        assert log.user_id == "anonymous"
        assert log.resource_id == ""
        assert log.metadata_json == "{}"
        assert log.ip_address == ""

    def test_serialization_round_trip(self):
        from app.audit.models import AuditLog, AuditLogResponse
        log = AuditLog(
            id=1,
            tenant_id="t1",
            user_id="u1",
            action="upload",
            resource_type="document",
            resource_id="d1",
            metadata_json='{"k":1}',
            ip_address="1.2.3.4",
            request_id="r1",
            created_at="2026-06-10T00:00:00Z",
        )
        # Pydantic v2: model_dump(mode='json') coerces datetime → ISO string
        data = log.model_dump(mode="json")
        assert data["user_id"] == "u1"
        assert isinstance(data["created_at"], str)
        # Response model accepts the same fields
        resp = AuditLogResponse(**data)
        assert resp.user_id == "u1"
        assert resp.created_at == "2026-06-10T00:00:00Z"


# ── service: end-to-end write+read ──
# Uses the singleton SQLite DB like test_memory.py. Each test creates a
# unique tenant_id to avoid cross-test interference, then queries back.


class TestAuditServiceE2E:
    def setup_method(self):
        from app.audit import init_audit_tables
        from app.memory.db import init_db
        init_db()
        init_audit_tables()

    def _tenant(self) -> str:
        return "audit_test_" + uuid.uuid4().hex[:8]

    @pytest.mark.asyncio
    async def test_record_audit_writes_to_db(self):
        from app.audit.models import AuditLog
        from app.audit.service import get_audit_logs, record_audit

        tenant = self._tenant()
        log = AuditLog(
            tenant_id=tenant,
            user_id="u-test",
            action="upload",
            resource_type="document",
            resource_id="d-test",
            metadata_json='{"k":"v"}',
            ip_address="10.0.0.1",
            request_id="r-test",
        )
        await record_audit(log)

        resp = get_audit_logs(tenant_id=tenant, limit=10)
        assert resp.total == 1
        assert len(resp.logs) == 1
        first = resp.logs[0]
        assert first.user_id == "u-test"
        assert first.action == "upload"
        assert first.resource_id == "d-test"
        assert first.ip_address == "10.0.0.1"
        assert first.request_id == "r-test"

    @pytest.mark.asyncio
    async def test_record_audit_swallows_db_errors(self):
        """If the DB write fails, record_audit must not raise — it logs a warning."""
        from app.audit.models import AuditLog
        from app.audit.service import record_audit

        log = AuditLog(action="query", resource_type="config")
        with patch(
            "app.audit.service._insert_audit",
            side_effect=RuntimeError("simulated db failure"),
        ):
            # Must not raise — audit failures are non-fatal by contract
            await record_audit(log)

    def test_get_audit_stats_aggregates_correctly(self):
        from app.audit.service import get_audit_stats
        from app.memory.db import get_db

        tenant = self._tenant()
        # Bypass async write path to inject known rows synchronously
        conn = get_db()
        now_iso = "2026-06-10T00:00:00+00:00"
        conn.execute(
            "INSERT INTO audit_logs (tenant_id, user_id, action, resource_type, resource_id, metadata_json, ip_address, request_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (tenant, "u1", "upload", "document", "d1", "{}", "", "", now_iso),
        )
        conn.execute(
            "INSERT INTO audit_logs (tenant_id, user_id, action, resource_type, resource_id, metadata_json, ip_address, request_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (tenant, "u2", "upload", "document", "d2", "{}", "", "", now_iso),
        )
        conn.execute(
            "INSERT INTO audit_logs (tenant_id, user_id, action, resource_type, resource_id, metadata_json, ip_address, request_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (tenant, "u3", "query", "config", "c1", "{}", "", "", now_iso),
        )
        conn.commit()

        from datetime import datetime, timezone
        fixed_now = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)  # same day as row timestamps
        stats = get_audit_stats(tenant_id=tenant, now=fixed_now)
        assert stats.total_logs == 3
        assert stats.actions == {"upload": 2, "query": 1}
        assert stats.resource_types == {"document": 2, "config": 1}
        # The 3 rows we just inserted are within the last 24h window
        assert stats.recent_count_24h == 3

    def test_get_audit_logs_pagination(self):
        from app.audit.service import get_audit_logs
        from app.memory.db import get_db

        tenant = self._tenant()
        conn = get_db()
        # Insert 5 rows
        for i in range(5):
            conn.execute(
                "INSERT INTO audit_logs (tenant_id, user_id, action, resource_type, resource_id, metadata_json, ip_address, request_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (tenant, f"u{i}", "upload", "document", f"d{i}", "{}", "", "", "2026-06-10T00:00:00+00:00"),
            )
        conn.commit()

        page1 = get_audit_logs(tenant_id=tenant, limit=2, offset=0)
        assert page1.total == 5
        assert len(page1.logs) == 2

        page2 = get_audit_logs(tenant_id=tenant, limit=2, offset=2)
        assert page2.total == 5
        assert len(page2.logs) == 2

        page3 = get_audit_logs(tenant_id=tenant, limit=2, offset=4)
        assert page3.total == 5
        assert len(page3.logs) == 1

    def test_get_audit_logs_tenant_isolation(self):
        """Logs from one tenant must never appear in another tenant's results."""
        from app.audit.service import get_audit_logs
        from app.memory.db import get_db

        tenant_a = self._tenant()
        tenant_b = self._tenant()
        conn = get_db()
        conn.execute(
            "INSERT INTO audit_logs (tenant_id, user_id, action, resource_type, resource_id, metadata_json, ip_address, request_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (tenant_a, "uA", "upload", "document", "dA", "{}", "", "", "2026-06-10T00:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO audit_logs (tenant_id, user_id, action, resource_type, resource_id, metadata_json, ip_address, request_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (tenant_b, "uB", "upload", "document", "dB", "{}", "", "", "2026-06-10T00:00:00+00:00"),
        )
        conn.commit()

        a = get_audit_logs(tenant_id=tenant_a, limit=10)
        b = get_audit_logs(tenant_id=tenant_b, limit=10)
        assert a.total == 1
        assert a.logs[0].user_id == "uA"
        assert b.total == 1
        assert b.logs[0].user_id == "uB"

    def test_get_audit_stats_empty_tenant_returns_zeros(self):
        from app.audit.service import get_audit_stats
        stats = get_audit_stats(tenant_id="nonexistent_" + uuid.uuid4().hex)
        assert stats.total_logs == 0
        assert stats.actions == {}
        assert stats.resource_types == {}
        assert stats.recent_count_1h == 0
        assert stats.recent_count_24h == 0
