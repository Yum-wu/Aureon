"""Tests for app.audit — security/compliance log system.

Covers the audit decorator (request-context extraction and fire-and-forget
write) and the read APIs (list + stats). DB-dependent tests require
PostgreSQL (DATABASE_URL).
"""

import json
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest

from app.config import settings


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
# Uses PostgreSQL. Each test creates a unique tenant_id to avoid interference.


class TestAuditServiceE2E:
    def _tenant(self) -> str:
        return "audit_test_" + uuid.uuid4().hex[:8]

    @asynccontextmanager
    async def _service_pool(self):
        pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=2)
        with patch("app.database.connection.get_db_pool", return_value=pool):
            try:
                yield
            finally:
                await pool.close()

    @pytest.mark.asyncio
    async def test_record_audit_writes_to_db(self):
        from app.audit.models import AuditLog
        from app.audit.service import get_audit_logs, record_audit

        tenant = self._tenant()
        async with self._service_pool():
            await record_audit(AuditLog(tenant_id=tenant, action="create", resource_type="document"))
            logs = await get_audit_logs(tenant_id=tenant)
        assert logs.total == 1
        assert logs.logs[0].action == "create"

    @pytest.mark.asyncio
    async def test_record_audit_swallows_db_errors(self):
        """If the DB write fails, record_audit must not raise — it logs a warning."""
        from app.audit.models import AuditLog
        from app.audit.service import record_audit

        log = AuditLog(action="query", resource_type="config")
        # Pool is None → record_audit logs warning and returns without raising
        with patch(
            "app.database.connection.get_db_pool",
            return_value=None,
        ):
            await record_audit(log)

    @pytest.mark.asyncio
    async def test_get_audit_stats_aggregates_correctly(self):
        from app.audit.models import AuditLog
        from app.audit.service import get_audit_stats, record_audit

        tenant = self._tenant()
        async with self._service_pool():
            await record_audit(AuditLog(tenant_id=tenant, action="create", resource_type="document"))
            await record_audit(AuditLog(tenant_id=tenant, action="delete", resource_type="document"))
            stats = await get_audit_stats(tenant_id=tenant)
        assert stats.total_logs == 2
        assert stats.actions["create"] == 1
        assert stats.actions["delete"] == 1
        assert stats.resource_types["document"] == 2

    @pytest.mark.asyncio
    async def test_get_audit_logs_pagination(self):
        from app.audit.models import AuditLog
        from app.audit.service import get_audit_logs, record_audit

        tenant = self._tenant()
        async with self._service_pool():
            for i in range(3):
                await record_audit(AuditLog(tenant_id=tenant, action=f"a{i}", resource_type="doc"))
            page = await get_audit_logs(tenant_id=tenant, limit=2, offset=1)
        assert page.total == 3
        assert page.limit == 2
        assert len(page.logs) == 2

    @pytest.mark.asyncio
    async def test_get_audit_logs_tenant_isolation(self):
        from app.audit.models import AuditLog
        from app.audit.service import get_audit_logs, record_audit

        tenant_a = self._tenant()
        tenant_b = self._tenant()
        async with self._service_pool():
            await record_audit(AuditLog(tenant_id=tenant_a, action="a", resource_type="doc"))
            await record_audit(AuditLog(tenant_id=tenant_b, action="b", resource_type="doc"))
            logs = await get_audit_logs(tenant_id=tenant_a)
        assert logs.total == 1
        assert logs.logs[0].tenant_id == tenant_a

    @pytest.mark.asyncio
    async def test_get_audit_stats_empty_tenant_returns_zeros(self):
        from app.audit.service import get_audit_stats

        async with self._service_pool():
            stats = await get_audit_stats(tenant_id=self._tenant())
        assert stats.total_logs == 0
        assert stats.actions == {}
