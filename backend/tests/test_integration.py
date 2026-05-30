"""Integration Ecosystem API Tests"""
import pytest
import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.integration import init_integration_tables


# 初始化数据库表
init_integration_tables()

client = TestClient(app)


class TestIntegrationConnectors:
    """Test Integration Connector endpoints"""

    def test_create_connector(self):
        """Test creating integration connector"""
        connector_name = f"connector-{uuid.uuid4().hex[:8]}"
        response = client.post(
            "/api/integration/connectors",
            json={
                "name": connector_name,
                "connector_type": "google_drive",
                "config": {"folder_id": "test-folder"},
                "sync_interval_minutes": 30,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == connector_name
        assert data["connector_type"] == "google_drive"

    def test_list_connectors(self):
        """Test listing integration connectors"""
        response = client.get("/api/integration/connectors")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_connector(self):
        """Test getting integration connector"""
        connector_name = f"connector-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/integration/connectors",
            json={"name": connector_name, "connector_type": "notion"},
        )
        response = client.get(f"/api/integration/connectors/{connector_name}")
        assert response.status_code == 200
        assert response.json()["name"] == connector_name

    def test_get_nonexistent_connector(self):
        """Test getting non-existent connector"""
        response = client.get("/api/integration/connectors/nonexistent")
        assert response.status_code == 404

    def test_delete_connector(self):
        """Test deleting integration connector"""
        connector_name = f"connector-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/integration/connectors",
            json={"name": connector_name, "connector_type": "github"},
        )
        response = client.delete(f"/api/integration/connectors/{connector_name}")
        assert response.status_code == 204

    def test_update_connector_status(self):
        """Test updating connector status"""
        connector_name = f"connector-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/integration/connectors",
            json={"name": connector_name, "connector_type": "sharepoint"},
        )
        response = client.put(
            f"/api/integration/connectors/{connector_name}/status",
            params={"status": "syncing"},
        )
        assert response.status_code == 200


class TestSyncLogs:
    """Test Sync Log endpoints"""

    def test_create_sync_log(self):
        """Test creating sync log"""
        response = client.post(
            "/api/integration/sync-logs",
            json={
                "connector_id": 1,
                "sync_type": "incremental",
                "status": "success",
                "documents_synced": 10,
            },
        )
        assert response.status_code == 201

    def test_list_sync_logs(self):
        """Test listing sync logs"""
        response = client.get("/api/integration/sync-logs")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data


class TestIMBots:
    """Test IM Bot endpoints"""

    def test_create_im_bot(self):
        """Test creating IM Bot config"""
        response = client.post(
            "/api/integration/im-bots",
            json={
                "platform": "slack",
                "workspace_id": "ws-123",
                "webhook_url": "https://hooks.slack.com/test",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["platform"] == "slack"
        assert data["workspace_id"] == "ws-123"

    def test_list_im_bots(self):
        """Test listing IM Bot configs"""
        response = client.get("/api/integration/im-bots")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_delete_im_bot(self):
        """Test deleting IM Bot config"""
        client.post(
            "/api/integration/im-bots",
            json={
                "platform": "teams",
                "workspace_id": "ws-456",
            },
        )
        response = client.delete("/api/integration/im-bots/teams/ws-456")
        assert response.status_code == 204

    def test_delete_nonexistent_im_bot(self):
        """Test deleting non-existent IM Bot"""
        response = client.delete("/api/integration/im-bots/slack/nonexistent")
        assert response.status_code == 404
