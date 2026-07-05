"""Observability API Tests"""
import pytest
from app.config import settings

skip_no_pg = pytest.mark.skipif(
    not settings.database_url,
    reason="Requires PostgreSQL (DATABASE_URL)",
)


@skip_no_pg
class TestObservabilityAPI:
    def test_list_traces(self, pg_client):
        response = pg_client.get("/api/observability/traces")
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "traces" in data
        assert isinstance(data["traces"], list)

    def test_list_traces_with_limit(self, pg_client):
        response = pg_client.get("/api/observability/traces?limit=5")
        assert response.status_code == 200
        assert len(response.json()["traces"]) <= 5

    def test_observability_stats(self, pg_client):
        response = pg_client.get("/api/observability/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_requests" in data
        assert "success_rate" in data
        assert "avg_total_latency_ms" in data
        assert "p95_total_latency_ms" in data
