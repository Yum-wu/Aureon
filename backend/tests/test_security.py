"""Security API Tests

RBAC bypass via conftest.py _bypass_rbac fixture (autouse).
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
)


# 初始化数据库表
init_pii_detection_table()
init_sso_providers_table()


@pytest.fixture
def client():
    """在 _bypass_rbac fixture 应用后创建 TestClient，确保 override 生效。"""
    return TestClient(app)


class TestPIIDetection:
    """Test PII Detection endpoints"""

    def test_detect_pii_email(self, client):
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

    def test_detect_pii_phone(self, client):
        """Test detecting phone PII"""
        response = client.post(
            "/api/security/pii/detect",
            params={"text": "Call me at 13812345678"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["pii_found"] is True
        assert data["results"][0]["type"] == "phone_cn"

    def test_detect_pii_none(self, client):
        """Test no PII found"""
        response = client.post(
            "/api/security/pii/detect",
            params={"text": "This is normal text without PII"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["pii_found"] is False
        assert len(data["results"]) == 0

    def test_mask_pii(self, client):
        """Test masking PII"""
        response = client.post(
            "/api/security/pii/mask",
            params={"text": "Email: test@example.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "***@***.***" in data["masked"]

    def test_scan_document(self, client):
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

    def test_create_sso_provider(self, client):
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

    def test_list_sso_providers(self, client):
        """Test listing SSO providers"""
        response = client.get("/api/security/sso/providers")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_delete_sso_provider(self, client):
        """Test deleting SSO provider"""
        provider_name = f"to-delete-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/security/sso/providers",
            json={"name": provider_name, "provider_type": "OIDC"},
        )
        response = client.delete(f"/api/security/sso/providers/{provider_name}")
        assert response.status_code == 204

    def test_delete_nonexistent_sso_provider(self, client):
        """Test deleting non-existent SSO provider"""
        response = client.delete("/api/security/sso/providers/nonexistent")
        assert response.status_code == 404


class TestSSOProviderDecryptionResilience:
    """Regression tests for graceful handling of unreadable SSO client_secrets.

    When ENCRYPTION_KEY is rotated (or the stored ciphertext is otherwise
    unreadable), list_sso_providers() and get_sso_provider() must NOT 500
    for the whole table — they should return a masked placeholder for the
    affected row and continue serving the rest.
    """

    def test_list_survives_corrupted_client_secret(self, client, monkeypatch):
        """A single unreadable client_secret must not break the whole list."""
        # Insert a row whose client_secret is ciphertext from a different key
        from cryptography.fernet import Fernet
        from app.security.sso import init_sso_providers_table
        from app.memory.db import get_db
        import uuid as _uuid

        init_sso_providers_table()
        other_key = Fernet.generate_key()
        bogus_ciphertext = Fernet(other_key).encrypt(b"encrypted-with-another-key").decode()
        name = f"corrupted-{_uuid.uuid4().hex[:8]}"

        conn = get_db()
        conn.execute(
            """INSERT INTO sso_providers
               (name, provider_type, client_id, client_secret, metadata_url, enabled, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, "SAML", "cid", bogus_ciphertext, None, 1, "2026-06-15T00:00:00Z"),
        )
        conn.commit()

        # Force the encryption module to re-init so the bogus ciphertext is
        # actually attempted to be decrypted.
        from app.security import encryption as enc_mod
        monkeypatch.setattr(enc_mod, "_fernet", None)

        response = client.get("/api/security/sso/providers")
        assert response.status_code == 200, response.text
        data = response.json()
        assert isinstance(data, list)
        # The corrupted row must appear with a masked placeholder, not raise
        corrupted = [p for p in data if p["name"] == name]
        assert len(corrupted) == 1
        assert "unreadable" in (corrupted[0]["client_secret"] or "")

    def test_get_survives_corrupted_client_secret(self, monkeypatch):
        """A single unreadable client_secret must not break get_sso_provider."""
        from cryptography.fernet import Fernet
        from app.security.sso import init_sso_providers_table, get_sso_provider
        from app.memory.db import get_db
        import uuid as _uuid

        init_sso_providers_table()
        other_key = Fernet.generate_key()
        bogus_ciphertext = Fernet(other_key).encrypt(b"encrypted-with-another-key").decode()
        name = f"corrupted-get-{_uuid.uuid4().hex[:8]}"

        conn = get_db()
        conn.execute(
            """INSERT INTO sso_providers
               (name, provider_type, client_id, client_secret, metadata_url, enabled, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, "OIDC", "cid", bogus_ciphertext, None, 1, "2026-06-15T00:00:00Z"),
        )
        conn.commit()

        from app.security import encryption as enc_mod
        monkeypatch.setattr(enc_mod, "_fernet", None)

        provider = get_sso_provider(name)
        assert provider is not None
        assert "unreadable" in (provider.client_secret or "")


class TestRateLimiting:
    """Test Rate Limiting endpoints"""

    def test_get_rate_limit_config(self, client):
        """Test getting rate limit config"""
        response = client.get("/api/security/rate-limits/config")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "requests_per_minute" in data
