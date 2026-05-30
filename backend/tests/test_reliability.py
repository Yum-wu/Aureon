"""Reliability API Tests"""
import pytest
import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.reliability import init_reliability_tables


# 初始化数据库表
init_reliability_tables()

client = TestClient(app)


class TestBackupManagement:
    """Test Backup Management endpoints"""

    def test_create_backup(self):
        """Test creating backup record"""
        response = client.post(
            "/api/reliability/backups",
            json={
                "backup_type": "full",
                "component": "vector_db",
                "file_size_bytes": 1024000,
            },
        )
        assert response.status_code == 201

    def test_list_backups(self):
        """Test listing backups"""
        response = client.get("/api/reliability/backups")
        assert response.status_code == 200
        data = response.json()
        assert "backups" in data


class TestIncidentManagement:
    """Test Incident Management endpoints"""

    def test_create_incident(self):
        """Test creating incident"""
        incident_id = f"inc-{uuid.uuid4().hex[:8]}"
        response = client.post(
            "/api/reliability/incidents",
            json={
                "incident_id": incident_id,
                "severity": "critical",
                "component": "llm",
                "title": "LLM provider timeout",
            },
        )
        assert response.status_code == 201

    def test_list_open_incidents(self):
        """Test listing open incidents"""
        response = client.get("/api/reliability/incidents/open")
        assert response.status_code == 200
        data = response.json()
        assert "incidents" in data

    def test_resolve_incident(self):
        """Test resolving incident"""
        incident_id = f"inc-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/reliability/incidents",
            json={
                "incident_id": incident_id,
                "severity": "warning",
                "component": "redis",
                "title": "Redis connection timeout",
            },
        )
        response = client.put(
            f"/api/reliability/incidents/{incident_id}/resolve",
            params={"resolution": "Increased connection pool size"},
        )
        assert response.status_code == 200


class TestSLOManagement:
    """Test SLO Management endpoints"""

    def test_create_slo(self):
        """Test creating SLO config"""
        metric_name = f"slo-{uuid.uuid4().hex[:8]}"
        response = client.post(
            "/api/reliability/slo",
            json={
                "metric_name": metric_name,
                "target_value": 99.9,
                "window_days": 30,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["metric_name"] == metric_name
        assert data["target_value"] == 99.9

    def test_list_slo_configs(self):
        """Test listing SLO configs"""
        response = client.get("/api/reliability/slo")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_slo_status(self):
        """Test getting SLO status"""
        response = client.get("/api/reliability/slo/status")
        assert response.status_code == 200
        data = response.json()
        assert "slos" in data
