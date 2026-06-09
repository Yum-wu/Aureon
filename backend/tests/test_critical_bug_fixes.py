"""Tests for the four critical-bug fixes:

1. SSO management endpoints require ADMIN role.
2. ``X-Tenant-ID`` header is rejected unless it matches an authenticated
   principal — prevents cross-tenant cache poisoning.
3. ``l2_scenario.finalize_scenario`` and ``offload.offload_if_needed`` reject
   session_ids that would escape the target directory (path-traversal).
4. The LLM classifier cache is bounded and prunes expired entries.
"""
from __future__ import annotations

import importlib
import os
import time
import uuid
from pathlib import Path

import pytest


# ────────────────────────────────────────────────────────────────────
# 1. SSO endpoints require ADMIN role
# ────────────────────────────────────────────────────────────────────


def test_sso_endpoints_require_admin_when_api_key_set(monkeypatch):
    """With API_AUTH_KEY configured, SSO routes must reject unauthenticated
    and non-admin callers."""
    monkeypatch.setenv("API_AUTH_KEY", "test-secret-key")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-for-sso-test")

    # Reset settings + security module singletons.
    from app.config import Settings
    import app.config as config_module
    config_module.settings = Settings()
    import app.security as sec_module
    importlib.reload(sec_module)
    import app.security.router as sec_router
    importlib.reload(sec_router)

    # Mount the SSO router on a minimal app (avoids loading the entire
    # main.py dependency tree).
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.security import create_access_token, UserRole

    app = FastAPI()
    app.include_router(sec_router.router)
    client = TestClient(app)

    # 1a. Unauthenticated call is rejected.
    resp = client.get("/sso/providers")
    assert resp.status_code in (401, 403), (
        f"Unauthenticated SSO list should be rejected, got {resp.status_code}"
    )

    resp = client.post(
        "/sso/providers",
        json={"name": f"x-{uuid.uuid4().hex[:6]}", "provider_type": "SAML"},
    )
    assert resp.status_code in (401, 403)

    resp = client.delete("/sso/providers/some-name")
    assert resp.status_code in (401, 403)

    # 1b. VIEWER token is rejected.
    viewer_token = create_access_token({"sub": "u1", "role": "VIEWER"})
    resp = client.get(
        "/sso/providers",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 403, (
        f"VIEWER should not access SSO list, got {resp.status_code}"
    )

    # 1c. EDITOR token is rejected.
    editor_token = create_access_token({"sub": "u1", "role": "EDITOR"})
    resp = client.get(
        "/sso/providers",
        headers={"Authorization": f"Bearer {editor_token}"},
    )
    assert resp.status_code == 403


# ────────────────────────────────────────────────────────────────────
# 2. X-Tenant-ID header spoofing is rejected
# ────────────────────────────────────────────────────────────────────


def test_x_tenant_id_header_cannot_spoof_other_tenant(monkeypatch):
    """A caller authenticated as tenant B must not be able to access tenant A
    by setting ``X-Tenant-ID: tenant-a``.

    To produce a real mismatch we need an authenticated principal, so we use
    a JWT whose ``tenant_id`` claim is ``tenant-b`` while the client header
    claims ``tenant-a``.
    """
    from fastapi.testclient import TestClient
    from app.security import create_access_token

    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-spoof-test-32bytes!!")
    monkeypatch.setenv("API_AUTH_KEY", "")

    # Reload settings + security modules so they pick up the new JWT_SECRET.
    from app.config import Settings
    import app.config as config_module
    config_module.settings = Settings()
    import app.security as sec_module
    importlib.reload(sec_module)
    import app.multi_tenant.middleware as mt_module
    importlib.reload(mt_module)
    from app.multi_tenant.middleware import TenantMiddleware

    # Token says caller is "tenant-b"; header says "tenant-a".
    token = create_access_token({"sub": "u1", "role": "EDITOR", "tenant_id": "tenant-b"})

    from starlette.requests import Request as StarletteRequest
    import asyncio

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/anything",
        "headers": [
            (b"authorization", f"Bearer {token}".encode()),
            (b"x-tenant-id", b"tenant-a"),
        ],
    }
    request = StarletteRequest(scope)

    async def call_next(_request):
        from starlette.responses import Response
        return Response(content='{"ok":true}', status_code=200)

    response = asyncio.run(TenantMiddleware(app=None).dispatch(request, call_next))
    assert response.status_code == 403, (
        f"Mismatched tenant header should be 403, got {response.status_code}"
    )
    assert "Tenant header" in response.body.decode()


def test_x_tenant_id_header_accepted_when_matches_principal(monkeypatch):
    """A caller authenticated as tenant A and sending X-Tenant-ID=tenant-a
    must be allowed through."""
    from app.security import create_access_token
    from starlette.requests import Request as StarletteRequest
    from starlette.responses import Response
    import asyncio

    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-match-test-32bytes!")
    monkeypatch.setenv("API_AUTH_KEY", "")
    from app.config import Settings
    import app.config as config_module
    config_module.settings = Settings()
    import app.security as sec_module
    importlib.reload(sec_module)
    import app.multi_tenant.middleware as mt_module
    importlib.reload(mt_module)
    from app.multi_tenant.middleware import (
        TenantMiddleware,
        TenantContext,
    )

    token = create_access_token({"sub": "u1", "role": "EDITOR", "tenant_id": "tenant-a"})

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/anything",
        "headers": [
            (b"authorization", f"Bearer {token}".encode()),
            (b"x-tenant-id", b"tenant-a"),
        ],
    }
    request = StarletteRequest(scope)

    seen = {}

    async def call_next(_request):
        seen["tenant_id"] = TenantContext.get_current_tenant_id()
        return Response(content='{"ok":true}', status_code=200)

    response = asyncio.run(TenantMiddleware(app=None).dispatch(request, call_next))
    assert response.status_code == 200
    assert seen["tenant_id"] == "tenant-a"


# ────────────────────────────────────────────────────────────────────
# 3. Path traversal is blocked in finalize_scenario and offload
# ────────────────────────────────────────────────────────────────────


def test_l2_finalize_blocks_path_traversal_in_session_id(tmp_path, monkeypatch):
    """A session_id containing ``..`` must not write outside SCENARIOS_DIR."""
    monkeypatch.chdir(tmp_path)
    # Force a fresh import so SCENARIOS_DIR is resolved under tmp_path.
    import app.memory.l2_scenario as l2
    importlib.reload(l2)
    l2.SCENARIOS_DIR = (tmp_path / "offloads" / "scenarios").resolve()
    l2.SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)

    target = tmp_path / "pwned_target.txt"
    l2.finalize_scenario(f"../{target.name}", summary="attack")
    # Nothing should have been written outside SCENARIOS_DIR.
    assert not target.exists(), "Path traversal write succeeded"
    assert list(l2.SCENARIOS_DIR.iterdir()) == []


def test_l2_finalize_blocks_unsafe_chars_in_session_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import app.memory.l2_scenario as l2
    importlib.reload(l2)
    l2.SCENARIOS_DIR = (tmp_path / "offloads" / "scenarios").resolve()
    l2.SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)

    # Path separators and empty strings must be rejected.  Resolved-path
    # check is what stops ``..``; the char filter is just a fast path.
    for bad in ("a/b", "a\\b", ""):
        l2.finalize_scenario(bad, summary="attack")
    assert list(l2.SCENARIOS_DIR.iterdir()) == []


def test_l2_finalize_blocks_dotdot_via_resolved_path_check(tmp_path, monkeypatch):
    """``..`` sequences must be caught by the resolved-path check, not just
    the character filter."""
    monkeypatch.chdir(tmp_path)
    import app.memory.l2_scenario as l2
    importlib.reload(l2)
    l2.SCENARIOS_DIR = (tmp_path / "offloads" / "scenarios").resolve()
    l2.SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)

    target = tmp_path / "pwned_dotdot.md"
    l2.finalize_scenario(f"../{target.name}", summary="attack")
    assert not target.exists()


def test_offload_blocks_path_traversal_in_session_id(tmp_path, monkeypatch):
    """offload_if_needed must refuse session_ids that would escape REFS_DIR."""
    monkeypatch.chdir(tmp_path)
    # Re-resolve REFS_DIR under tmp_path.
    import app.memory.offload as off
    importlib.reload(off)
    off.REFS_DIR = (tmp_path / "offloads" / "refs").resolve()
    off.REFS_DIR.mkdir(parents=True, exist_ok=True)

    # Make sure settings has a small offload threshold so the function
    # actually attempts the write path.
    from app.config import Settings
    import app.config as config_module
    config_module.settings = Settings(offload_max_chars=10)
    importlib.reload(off)

    target = tmp_path / "pwned_offload.md"
    long_content = "x" * 1000
    result = off.offload_if_needed(
        tool_name="x", content=long_content, session_id=f"../{target.name}",
    )
    # The unsafe call should fall back to returning the original content,
    # NOT a result_ref pointing at the traversal target.
    assert "result_ref" not in result
    assert not target.exists()


# ────────────────────────────────────────────────────────────────────
# 4. Classifier cache is bounded
# ────────────────────────────────────────────────────────────────────


def test_classifier_cache_is_bounded(monkeypatch):
    """Insert more than the cache max and verify the cache size stays bounded."""
    import app.rag.qa_chain as qa
    importlib.reload(qa)
    monkeypatch.setattr(qa, "_CLASSIFIER_CACHE_MAX", 4)
    monkeypatch.setattr(qa, "_CLASSIFIER_CACHE_TTL", 3600)
    # Clear in case other tests populated it.
    qa._CLASSIFIER_CACHE.clear()
    qa._CLASSIFIER_CACHE_TIMESTAMPS.clear()

    for i in range(20):
        qa._classifier_cache_set(f"query-{i}", bool(i % 2))

    assert len(qa._CLASSIFIER_CACHE) <= qa._CLASSIFIER_CACHE_MAX
    # Most-recent entry should be present.
    assert qa._classifier_cache_get("query-19") is not None
    # Oldest entry should have been evicted.
    assert qa._classifier_cache_get("query-0") is None


def test_classifier_cache_prunes_expired_entries(monkeypatch):
    """Expired entries are removed on read, not just left to accumulate."""
    import app.rag.qa_chain as qa
    importlib.reload(qa)
    monkeypatch.setattr(qa, "_CLASSIFIER_CACHE_TTL", 0.05)
    qa._CLASSIFIER_CACHE.clear()
    qa._CLASSIFIER_CACHE_TIMESTAMPS.clear()

    qa._classifier_cache_set("alpha", True)
    assert qa._classifier_cache_get("alpha") is True
    time.sleep(0.1)
    # Now expired — get() must return None AND remove the entry.
    assert qa._classifier_cache_get("alpha") is None
    assert "alpha" not in qa._CLASSIFIER_CACHE
    assert "alpha" not in qa._CLASSIFIER_CACHE_TIMESTAMPS
