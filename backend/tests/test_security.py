"""Security API Tests

Uses FastAPI dependency_overrides to bypass RBAC in tests.
"""
import os
import pytest
import uuid

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only")

from fastapi.testclient import TestClient
from app.main import app
from app.security import (
    init_pii_detection_table,
    init_sso_providers_table,
    UserRole,
)


# 初始化数据库表
init_pii_detection_table()
init_sso_providers_table()


@pytest.fixture(autouse=True)
def _bypass_rbac():
    """Bypass all require_role RBAC checks during tests."""
    mock_user = {"sub": "test-user", "role": "ADMIN", "_role": UserRole.ADMIN}

    overrides = {}
    for route in app.routes:
        if not hasattr(route, "dependant"):
            continue
        for dep in route.dependant.dependencies:
            call = dep.call
            if getattr(call, "__name__", "") == "_role_checker":
                async def _mock_admin(_original_call=call):
                    return mock_user
                overrides[call] = _mock_admin

    for dep_func, mock_func in overrides.items():
        app.dependency_overrides[dep_func] = mock_func

    yield

    for dep_func in overrides:
        app.dependency_overrides.pop(dep_func, None)


client = TestClient(app)


class TestPIIDetection:
    """Test PII Detection endpoints"""

    def test_detect_pii_email(self):
        """Test detecting email PII"""
        response = client.post(
            "/api/security/pii/detect",
            params={"text": "Contact me at test@example.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["pii_found"] is True
        assert len(data["results"]) == 1
        assert data["results"][0]["type"] == "email"

    def test_detect_pii_phone(self):
        """Test detecting phone PII"""
        response = client.post(
            "/api/security/pii/detect",
            params={"text": "Call me at 13812345678"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["pii_found"] is True
        assert data["results"][0]["type"] == "phone_cn"

    def test_detect_pii_none(self):
        """Test no PII found"""
        response = client.post(
            "/api/security/pii/detect",
            params={"text": "This is normal text without PII"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["pii_found"] is False
        assert len(data["results"]) == 0

    def test_mask_pii(self):
        """Test masking PII"""
        response = client.post(
            "/api/security/pii/mask",
            params={"text": "Email: test@example.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "***@***.***" in data["masked"]

    def test_scan_document(self):
        """Test scanning document for PII"""
        response = client.post(
            "/api/security/pii/scan-document",
            params={
                "document_id": "doc-123",
                "content": "User email is test@example.com",
                "action": "mask",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["pii_count"] == 1
        assert data["document_id"] == "doc-123"


class TestSSOProviders:
    """Test SSO Provider endpoints"""

    def test_create_sso_provider(self):
        """Test creating SSO provider"""
        provider_name = f"test-okta-{uuid.uuid4().hex[:8]}"
        response = client.post(
            "/api/security/sso/providers",
            json={
                "name": provider_name,
                "provider_type": "SAML",
                "client_id": "test-client-id",
                "enabled": True,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == provider_name
        assert data["provider_type"] == "SAML"

    def test_list_sso_providers(self):
        """Test listing SSO providers"""
        response = client.get("/api/security/sso/providers")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_delete_sso_provider(self):
        """Test deleting SSO provider"""
        provider_name = f"to-delete-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/security/sso/providers",
            json={"name": provider_name, "provider_type": "OIDC"},
        )
        response = client.delete(f"/api/security/sso/providers/{provider_name}")
        assert response.status_code == 204

    def test_delete_nonexistent_sso_provider(self):
        """Test deleting non-existent SSO provider"""
        response = client.delete("/api/security/sso/providers/nonexistent")
        assert response.status_code == 404


class TestRateLimiting:
    """Test Rate Limiting endpoints"""

    def test_get_rate_limit_config(self):
        """Test getting rate limit config"""
        response = client.get("/api/security/rate-limits/config")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "requests_per_minute" in data
