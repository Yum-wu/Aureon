"""Cost Governance API Tests"""
import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.cost import init_cost_tables


# 初始化数据库表
init_cost_tables()

client = TestClient(app)


class TestCostTracking:
    """Test Cost Tracking endpoints"""

    def test_record_cost(self):
        """Test recording cost"""
        response = client.post(
            "/api/cost/records",
            json={
                "workspace_id": "ws-123",
                "user_id": "user-1",
                "tokens_input": 500,
                "tokens_output": 200,
                "model_used": "gpt-4o-mini",
            },
        )
        assert response.status_code == 201

    def test_workspace_cost(self):
        """Test getting workspace cost"""
        response = client.get("/api/cost/workspace/ws-123")
        assert response.status_code == 200
        data = response.json()
        assert "total_queries" in data
        assert "total_cost_usd" in data

    def test_user_cost(self):
        """Test getting user cost"""
        response = client.get("/api/cost/user/user-1")
        assert response.status_code == 200
        data = response.json()
        assert "total_queries" in data

    def test_top_users(self):
        """Test getting top users"""
        response = client.get("/api/cost/workspace/ws-123/top-users")
        assert response.status_code == 200
        data = response.json()
        assert "users" in data


class TestBudgetManagement:
    """Test Budget Management endpoints"""

    def test_create_budget(self):
        """Test creating budget"""
        workspace_id = f"ws-{uuid.uuid4().hex[:8]}"
        response = client.post(
            "/api/cost/budgets",
            json={
                "workspace_id": workspace_id,
                "monthly_limit_usd": 100.0,
                "warning_threshold": 0.8,
                "enforcement": "warn",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["monthly_limit_usd"] == 100.0

    def test_get_budget(self):
        """Test getting budget"""
        workspace_id = f"ws-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/cost/budgets",
            json={"workspace_id": workspace_id, "monthly_limit_usd": 50.0},
        )
        response = client.get(f"/api/cost/budgets/{workspace_id}")
        assert response.status_code == 200
        assert response.json()["monthly_limit_usd"] == 50.0

    def test_get_nonexistent_budget(self):
        """Test getting non-existent budget"""
        response = client.get("/api/cost/budgets/nonexistent")
        assert response.status_code == 404

    def test_update_budget(self):
        """Test updating budget"""
        workspace_id = f"ws-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/cost/budgets",
            json={"workspace_id": workspace_id, "monthly_limit_usd": 50.0},
        )
        response = client.put(
            f"/api/cost/budgets/{workspace_id}",
            json={"monthly_limit_usd": 200.0},
        )
        assert response.status_code == 200
        assert response.json()["monthly_limit_usd"] == 200.0

    def test_budget_status(self):
        """Test getting budget status"""
        workspace_id = f"ws-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/cost/budgets",
            json={"workspace_id": workspace_id, "monthly_limit_usd": 100.0},
        )
        response = client.get(f"/api/cost/budgets/{workspace_id}/status")
        assert response.status_code == 200
        data = response.json()
        assert data["has_budget"] is True
        assert data["monthly_limit_usd"] == 100.0
