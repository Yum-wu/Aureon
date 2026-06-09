"""Security API Tests"""
import pytest
import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.security import init_pii_detection_table, init_sso_providers_table


# 初始化数据库表
init_pii_detection_table()
init_sso_providers_table()

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


def _admin_headers():
    """Return Authorization headers with an ADMIN JWT for SSO tests.

    SSO management endpoints now require ADMIN role (security fix).
    In dev mode (no API_AUTH_KEY), require_role returns a dev-user with
    ADMIN role, so no header is needed.  When API_AUTH_KEY is set, we
    must provide a valid ADMIN JWT.
    """
    from app.config import settings
    if not settings.api_auth_key:
        return {}
    from app.security import create_access_token
    token = create_access_token({"sub": "test-admin", "role": "ADMIN"})
    return {"Authorization": f"Bearer {token}"}


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
            headers=_admin_headers(),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == provider_name
        assert data["provider_type"] == "SAML"

    def test_list_sso_providers(self):
        """Test listing SSO providers"""
        response = client.get(
            "/api/security/sso/providers",
            headers=_admin_headers(),
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_delete_sso_provider(self):
        """Test deleting SSO provider"""
        provider_name = f"to-delete-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/security/sso/providers",
            json={"name": provider_name, "provider_type": "OIDC"},
            headers=_admin_headers(),
        )
        response = client.delete(
            f"/api/security/sso/providers/{provider_name}",
            headers=_admin_headers(),
        )
        assert response.status_code == 204

    def test_delete_nonexistent_sso_provider(self):
        """Test deleting non-existent SSO provider"""
        response = client.delete(
            "/api/security/sso/providers/nonexistent",
            headers=_admin_headers(),
        )
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
