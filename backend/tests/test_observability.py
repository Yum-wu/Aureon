"""Observability API Tests"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.observability import init_query_traces_table, QueryTrace, save_query_trace


# 初始化数据库表
init_query_traces_table()

client = TestClient(app)


class TestObservabilityAPI:
    """Test Observability endpoints"""

    def test_list_traces(self):
        """Test listing traces"""
        response = client.get("/api/observability/traces")
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "traces" in data
        assert isinstance(data["traces"], list)

    def test_list_traces_with_limit(self):
        """Test listing traces with limit"""
        response = client.get("/api/observability/traces?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["traces"]) <= 5

    def test_observability_stats(self):
        """Test observability stats"""
        response = client.get("/api/observability/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_requests" in data
        assert "success_rate" in data
        assert "avg_total_latency_ms" in data
        assert "p95_total_latency_ms" in data
