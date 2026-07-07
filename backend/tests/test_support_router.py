"""Tests for public support helper endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.security.rbac import verify_token


@pytest.mark.asyncio
async def test_support_session_is_public_when_api_auth_enabled(monkeypatch):
    """Visitors need a scoped WS token before they can open support chat."""
    from app.config import settings

    monkeypatch.setattr(settings.auth, "api_auth_key", "test-api-key")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/v1/support/session")

    assert resp.status_code == 200
    data = resp.json()
    assert data["token_type"] == "bearer"
    assert data["expires_in"] <= 900

    payload = verify_token(data["access_token"])
    assert payload["sub"] == "support-visitor"
    assert payload["scope"] == "support_ws"
