"""Knowledge Intelligence API Tests"""
import pytest
import uuid
import hashlib
from fastapi.testclient import TestClient
from app.main import app
from app.knowledge import init_knowledge_tables


# 初始化数据库表
init_knowledge_tables()

client = TestClient(app)


class TestDocumentVersionControl:
    """Test Document Version Control endpoints"""

    def test_create_version(self):
        """Test creating document version"""
        doc_id = f"doc-{uuid.uuid4().hex[:8]}"
        content_hash = hashlib.sha256(b"test content").hexdigest()
        response = client.post(
            "/api/knowledge/versions",
            json={
                "document_id": doc_id,
                "version": 1,
                "content_hash": content_hash,
                "content_preview": "Test content preview",
                "changes_summary": "Initial version",
            },
        )
        assert response.status_code == 201

    def test_list_versions(self):
        """Test listing document versions"""
        doc_id = f"doc-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/knowledge/versions",
            json={
                "document_id": doc_id,
                "version": 1,
                "content_hash": "hash1",
            },
        )
        response = client.get(f"/api/knowledge/versions/{doc_id}")
        assert response.status_code == 200
        data = response.json()
        assert "versions" in data
        assert len(data["versions"]) == 1

    def test_get_latest_version(self):
        """Test getting latest version"""
        doc_id = f"doc-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/knowledge/versions",
            json={"document_id": doc_id, "version": 1, "content_hash": "hash1"},
        )
        client.post(
            "/api/knowledge/versions",
            json={"document_id": doc_id, "version": 2, "content_hash": "hash2"},
        )
        response = client.get(f"/api/knowledge/versions/{doc_id}/latest")
        assert response.status_code == 200
        assert response.json()["version"] == 2

    def test_get_nonexistent_version(self):
        """Test getting non-existent version"""
        response = client.get("/api/knowledge/versions/nonexistent/latest")
        assert response.status_code == 404


class TestExportManagement:
    """Test Export Management endpoints"""

    def test_create_export(self):
        """Test creating export record"""
        response = client.post(
            "/api/knowledge/exports",
            json={
                "export_type": "query_history",
                "format": "csv",
                "date_range_days": 30,
            },
        )
        assert response.status_code == 201

    def test_list_exports(self):
        """Test listing exports"""
        response = client.get("/api/knowledge/exports")
        assert response.status_code == 200
        data = response.json()
        assert "exports" in data

    def test_complete_export(self):
        """Test completing export"""
        record = client.post(
            "/api/knowledge/exports",
            json={"export_type": "analytics", "format": "json"},
        ).json()
        response = client.put(
            f"/api/knowledge/exports/{record['id']}/complete",
            params={"status": "completed", "file_path": "/exports/analytics.json", "file_size": 1024},
        )
        assert response.status_code == 200
