"""Reliability API Tests"""
import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

skip_no_pg = pytest.mark.skipif(
    not settings.database_url,
    reason="Requires PostgreSQL (DATABASE_URL)",
)


@pytest.mark.skip(reason="Requires PostgreSQL (DATABASE_URL)")
class TestBackupManagement:
    def test_create_backup(self, pg_client):
        response = pg_client.post(
            "/api/reliability/backups",
            json={"backup_type": "full", "component": "vector_db", "file_size_bytes": 1024000},
        )
        assert response.status_code == 201

    def test_list_backups(self, pg_client):
        response = pg_client.get("/api/reliability/backups")
        assert response.status_code == 200
        assert "backups" in response.json()


@skip_no_pg
class TestIncidentManagement:
    def test_create_incident(self, pg_client):
        incident_id = f"inc-{uuid.uuid4().hex[:8]}"
        response = pg_client.post(
            "/api/reliability/incidents",
            json={
                "incident_id": incident_id,
                "severity": "critical",
                "component": "llm",
                "title": "LLM provider timeout",
            },
        )
        assert response.status_code == 201

    def test_list_open_incidents(self, pg_client):
        response = pg_client.get("/api/reliability/incidents/open")
        assert response.status_code == 200
        assert "incidents" in response.json()

    def test_resolve_incident(self, pg_client):
        incident_id = f"inc-{uuid.uuid4().hex[:8]}"
        pg_client.post(
            "/api/reliability/incidents",
            json={
                "incident_id": incident_id,
                "severity": "warning",
                "component": "redis",
                "title": "Redis connection timeout",
            },
        )
        response = pg_client.put(
            f"/api/reliability/incidents/{incident_id}/resolve",
            params={"resolution": "Increased connection pool size"},
        )
        assert response.status_code == 200


@skip_no_pg
class TestSLOManagement:
    def test_create_slo(self, pg_client):
        metric_name = f"slo-{uuid.uuid4().hex[:8]}"
        response = pg_client.post(
            "/api/reliability/slo",
            json={"metric_name": metric_name, "target_value": 99.9, "window_days": 30},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["metric_name"] == metric_name
        assert abs(data["target_value"] - 99.9) < 0.001

    def test_list_slo_configs(self, pg_client):
        response = pg_client.get("/api/reliability/slo")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_slo_status(self, pg_client):
        response = pg_client.get("/api/reliability/slo/status")
        assert response.status_code == 200
        assert "slos" in response.json()
