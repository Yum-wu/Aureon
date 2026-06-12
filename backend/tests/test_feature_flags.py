"""Feature Flags API Tests"""
import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.features import init_feature_flags_table


# 初始化数据库表
init_feature_flags_table()

client = TestClient(app)


class TestFeatureFlagAPI:
    """Test Feature Flag CRUD operations"""

    def test_create_flag(self):
        """Test creating a new feature flag"""
        flag_name = f"test-flag-{uuid.uuid4().hex[:8]}"
        response = client.post(
            "/api/feature-flags/",
            json={"name": flag_name, "description": "Test flag", "enabled": True},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == flag_name
        assert data["enabled"] is True
        assert data["status"] == "draft"

    def test_create_duplicate_flag(self):
        """Test creating duplicate flag returns 409"""
        flag_name = f"duplicate-flag-{uuid.uuid4().hex[:8]}"
        client.post("/api/feature-flags/", json={"name": flag_name})
        response = client.post(
            "/api/feature-flags/", json={"name": flag_name}
        )
        assert response.status_code == 409

    def test_get_flag(self):
        """Test getting a flag by name"""
        flag_name = f"get-flag-{uuid.uuid4().hex[:8]}"
        client.post("/api/feature-flags/", json={"name": flag_name})
        response = client.get(f"/api/feature-flags/{flag_name}")
        assert response.status_code == 200
        assert response.json()["name"] == flag_name

    def test_get_nonexistent_flag(self):
        """Test getting non-existent flag returns 404"""
        response = client.get("/api/feature-flags/nonexistent")
        assert response.status_code == 404

    def test_list_flags(self):
        """Test listing all flags"""
        response = client.get("/api/feature-flags/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_update_flag(self):
        """Test updating a flag"""
        flag_name = f"update-flag-{uuid.uuid4().hex[:8]}"
        client.post("/api/feature-flags/", json={"name": flag_name})
        response = client.put(
            f"/api/feature-flags/{flag_name}",
            json={"enabled": True, "percentage": 50},
        )
        assert response.status_code == 200
        assert response.json()["enabled"] is True
        assert response.json()["percentage"] == 50

    def test_delete_flag(self):
        """Test deleting a flag"""
        flag_name = f"delete-flag-{uuid.uuid4().hex[:8]}"
        client.post("/api/feature-flags/", json={"name": flag_name})
        response = client.delete(f"/api/feature-flags/{flag_name}")
        assert response.status_code == 204

    def test_evaluate_flag(self):
        """Test evaluating a flag"""
        flag_name = f"eval-flag-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/feature-flags/",
            json={"name": flag_name, "enabled": True, "percentage": 100},
        )
        # Activate the flag
        client.put(
            f"/api/feature-flags/{flag_name}",
            json={"status": "active"},
        )
        response = client.get(f"/api/feature-flags/evaluate/{flag_name}")
        assert response.status_code == 200
        assert response.json()["enabled"] is True
