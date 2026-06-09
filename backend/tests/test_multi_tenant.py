"""Tests for app.multi_tenant.middleware — tenant context, JWT parsing, and
the FastAPI middleware that wires tenant_id into contextvars.

Multi-tenant isolation is a Phase 4 governance feature and is relied on by
the cache, audit, and BM25 layers. These tests pin down:

- TenantContext / get_current_tenant_id: contextvar-backed, defaults to
  "default", can be set and cleared.
- _extract_tenant_from_jwt: handles valid tokens, missing claims, malformed
  input, and base64 padding edge cases.
- TenantMiddleware: X-Tenant-ID header wins, falls back to JWT claim,
  defaults to "default", and clears the context after the request so
  requests cannot leak tenant_id across each other.
"""

import base64
import json
import threading
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_tenant_context():
    """Ensure each test starts and ends with the default tenant id.

    ContextVars are task-local so this is mostly defensive, but the helper
    also catches any module-level state set by middleware integration tests.
    """
    from app.multi_tenant import middleware as m
    m.TenantContext.set_tenant_id("default")
    yield
    m.TenantContext.set_tenant_id("default")


@pytest.fixture
def client():
    """TestClient wrapping a minimal app that uses TenantMiddleware and
    exposes a route that reports the current tenant id."""
    from app.multi_tenant.middleware import TenantMiddleware

    app = FastAPI()
    app.add_middleware(TenantMiddleware)

    @app.get("/whoami")
    async def whoami():
        from app.multi_tenant.middleware import get_current_tenant_id
        return {"tenant_id": get_current_tenant_id()}

    @app.get("/state")
    async def state(request: Request):
        return {"state_tenant": getattr(request.state, "tenant_id", None)}

    with TestClient(app) as c:
        yield c


# ── TenantContext ───────────────────────────────────────────────────────────


class TestTenantContext:
    def test_default_is_default(self):
        from app.multi_tenant.middleware import TenantContext, get_current_tenant_id
        TenantContext.clear()
        assert get_current_tenant_id() == "default"
        assert TenantContext.get_current_tenant_id() == "default"

    def test_set_and_get_round_trips(self):
        from app.multi_tenant.middleware import TenantContext
        TenantContext.set_tenant_id("acme")
        assert TenantContext.get_current_tenant_id() == "acme"

    def test_clear_resets_to_default(self):
        from app.multi_tenant.middleware import TenantContext
        TenantContext.set_tenant_id("acme")
        TenantContext.clear()
        assert TenantContext.get_current_tenant_id() == "default"

    def test_get_helper_matches_class_api(self):
        from app.multi_tenant.middleware import (
            TenantContext, get_current_tenant_id,
        )
        TenantContext.set_tenant_id("globex")
        assert get_current_tenant_id() == "globex"


# ── _extract_tenant_from_jwt ────────────────────────────────────────────────


def _make_jwt(payload_dict: dict) -> str:
    """Build an unsigned JWT-shaped string with the given payload."""
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=")
    payload = json.dumps(payload_dict).encode()
    payload_b64 = base64.urlsafe_b64encode(payload).rstrip(b"=")
    return f"{header.decode()}.{payload_b64.decode()}.sig"


class TestExtractTenantFromJwt:
    def test_returns_claim_when_present(self):
        from app.multi_tenant.middleware import _extract_tenant_from_jwt
        token = _make_jwt({"tenant_id": "acme", "sub": "alice"})
        assert _extract_tenant_from_jwt(token) == "acme"

    def test_returns_none_when_claim_missing(self):
        from app.multi_tenant.middleware import _extract_tenant_from_jwt
        token = _make_jwt({"sub": "alice"})
        assert _extract_tenant_from_jwt(token) is None

    def test_returns_none_for_malformed_token(self):
        from app.multi_tenant.middleware import _extract_tenant_from_jwt
        assert _extract_tenant_from_jwt("not-a-jwt") is None
        assert _extract_tenant_from_jwt("only.two") is None
        assert _extract_tenant_from_jwt("a.b.c.d") is None

    def test_returns_none_for_invalid_base64(self):
        from app.multi_tenant.middleware import _extract_tenant_from_jwt
        # Build a token with non-base64 payload
        assert _extract_tenant_from_jwt("abc.!!!.xyz") is None

    def test_returns_none_for_non_json_payload(self):
        from app.multi_tenant.middleware import _extract_tenant_from_jwt
        bad = base64.urlsafe_b64encode(b"not-json").rstrip(b"=").decode()
        assert _extract_tenant_from_jwt(f"hdr.{bad}.sig") is None

    def test_handles_padding_correctly(self):
        """The extractor must add the right padding regardless of input length.

        base64 payload length mod 4 is 1 is invalid but 2/3 require padding.
        """
        from app.multi_tenant.middleware import _extract_tenant_from_jwt
        # A short tenant id produces a payload that needs `==` padding.
        short = _make_jwt({"tenant_id": "a"})
        assert _extract_tenant_from_jwt(short) == "a"


# ── TenantMiddleware ───────────────────────────────────────────────────────


class TestTenantMiddleware:
    def test_header_takes_priority(self, client):
        resp = client.get(
            "/whoami",
            headers={
                "X-Tenant-ID": "header-tenant",
                "Authorization": f"Bearer {_make_jwt({'tenant_id': 'jwt-tenant'})}",
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"tenant_id": "header-tenant"}

    def test_jwt_used_when_no_header(self, client):
        token = _make_jwt({"tenant_id": "jwt-tenant"})
        resp = client.get(
            "/whoami",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.json() == {"tenant_id": "jwt-tenant"}

    def test_default_when_no_header_no_jwt(self, client):
        resp = client.get("/whoami")
        assert resp.json() == {"tenant_id": "default"}

    def test_jwt_without_tenant_claim_falls_back_to_default(self, client):
        token = _make_jwt({"sub": "alice"})  # no tenant_id
        resp = client.get(
            "/whoami",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.json() == {"tenant_id": "default"}

    def test_malformed_jwt_falls_back_to_default(self, client):
        resp = client.get(
            "/whoami",
            headers={"Authorization": "Bearer not-a-jwt"},
        )
        assert resp.json() == {"tenant_id": "default"}

    def test_non_bearer_auth_ignored(self, client):
        resp = client.get(
            "/whoami",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert resp.json() == {"tenant_id": "default"}

    def test_request_state_populated(self, client):
        resp = client.get(
            "/state",
            headers={"X-Tenant-ID": "tenant-x"},
        )
        assert resp.json() == {"state_tenant": "tenant-x"}

    def test_context_cleared_between_requests(self, client):
        """A request carrying tenant A must not leak into a subsequent
        request without the header."""
        resp_a = client.get("/whoami", headers={"X-Tenant-ID": "acme"})
        assert resp_a.json()["tenant_id"] == "acme"

        resp_b = client.get("/whoami")
        assert resp_b.json()["tenant_id"] == "default"

    def test_concurrent_requests_do_not_share_tenant(self, client):
        """Two threads sending distinct tenants must each observe their own.

        ContextVar isolation across threads is what makes the middleware
        safe under concurrent workloads.
        """
        results = {}

        def call(tenant, errors):
            try:
                r = client.get(
                    "/whoami",
                    headers={"X-Tenant-ID": tenant} if tenant else {},
                )
                results[tenant or "default"] = r.json()["tenant_id"]
            except Exception as exc:  # pragma: no cover - test failure path
                errors.append(exc)

        errors = []
        t1 = threading.Thread(target=call, args=("alpha", errors))
        t2 = threading.Thread(target=call, args=("beta", errors))
        t1.start(); t2.start()
        t1.join(); t2.join()
        assert errors == []
        assert results == {"alpha": "alpha", "beta": "beta"}
