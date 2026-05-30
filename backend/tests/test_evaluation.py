"""Evaluation Dashboard API Tests"""
import pytest
import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.evaluation import init_evaluation_tables


# 初始化数据库表
init_evaluation_tables()

client = TestClient(app)


class TestEvaluationMetrics:
    """Test Evaluation Metrics endpoints"""

    def test_create_metric(self):
        """Test creating evaluation metric"""
        response = client.post(
            "/api/evaluation/metrics",
            json={
                "metric_name": "recall_at_3",
                "metric_value": 0.96,
                "metric_type": "recall",
                "benchmark_set": "qa-51",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "created"

    def test_list_metrics(self):
        """Test listing evaluation metrics"""
        response = client.get("/api/evaluation/metrics")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["metrics"], list)

    def test_list_metrics_by_type(self):
        """Test listing metrics by type"""
        response = client.get("/api/evaluation/metrics?metric_type=recall")
        assert response.status_code == 200

    def test_evaluation_summary(self):
        """Test evaluation summary"""
        response = client.get("/api/evaluation/summary")
        assert response.status_code == 200
        data = response.json()
        assert "latest_recall_at_3" in data
        assert "latest_faithfulness" in data
        assert "latest_hallucination_rate" in data
        assert "total_runs" in data


class TestBenchmarkRuns:
    """Test Benchmark Runs endpoints"""

    def test_create_benchmark_run(self):
        """Test creating benchmark run"""
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        response = client.post(
            "/api/evaluation/benchmarks",
            json={
                "run_id": run_id,
                "benchmark_set": "qa-51",
                "total_queries": 51,
                "successful_queries": 49,
                "recall_at_3": 0.96,
                "status": "completed",
            },
        )
        assert response.status_code == 201

    def test_list_benchmark_runs(self):
        """Test listing benchmark runs"""
        response = client.get("/api/evaluation/benchmarks")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["runs"], list)

    def test_list_benchmark_runs_by_set(self):
        """Test listing benchmark runs by set"""
        response = client.get("/api/evaluation/benchmarks?benchmark_set=qa-51")
        assert response.status_code == 200
