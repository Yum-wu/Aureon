"""AI Platform API Tests"""
import pytest
import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.ai_platform import init_ai_platform_tables


# 初始化数据库表
init_ai_platform_tables()

client = TestClient(app)


class TestLLMProviders:
    """Test LLM Provider endpoints"""

    def test_create_provider(self):
        """Test creating LLM provider"""
        provider_name = f"provider-{uuid.uuid4().hex[:8]}"
        response = client.post(
            "/api/ai-platform/providers",
            json={
                "name": provider_name,
                "provider_type": "openai",
                "model_name": "gpt-4o",
                "api_key": "test-key",
                "enabled": True,
                "priority": 0,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == provider_name
        assert data["provider_type"] == "openai"

    def test_list_providers(self):
        """Test listing LLM providers"""
        response = client.get("/api/ai-platform/providers")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_delete_provider(self):
        """Test deleting LLM provider"""
        provider_name = f"provider-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/ai-platform/providers",
            json={
                "name": provider_name,
                "provider_type": "openai",
                "model_name": "gpt-4o",
            },
        )
        response = client.delete(f"/api/ai-platform/providers/{provider_name}")
        assert response.status_code == 204

    def test_delete_nonexistent_provider(self):
        """Test deleting non-existent provider"""
        response = client.delete("/api/ai-platform/providers/nonexistent")
        assert response.status_code == 404


class TestConfidenceScoring:
    """Test Confidence Scoring endpoints"""

    def test_calculate_confidence(self):
        """Test calculating confidence score"""
        response = client.post(
            "/api/ai-platform/confidence/calculate",
            params={"query": "test query"},
            json={
                "retrieved_chunks": [{"id": 1}, {"id": 2}, {"id": 3}],
                "cited_chunks": [{"id": 1}, {"id": 2}],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "confidence_score" in data
        assert "citation_coverage" in data

    def test_save_confidence(self):
        """Test saving confidence score"""
        response = client.post(
            "/api/ai-platform/confidence",
            json={
                "query_id": f"q-{uuid.uuid4().hex[:8]}",
                "query": "test query",
                "confidence_score": 0.85,
                "citation_coverage": 0.8,
                "retrieved_chunks": 3,
                "cited_chunks": 2,
            },
        )
        assert response.status_code == 201


class TestConversation:
    """Test Conversation endpoints"""

    def test_create_session(self):
        """Test creating conversation session"""
        session_id = f"session-{uuid.uuid4().hex[:8]}"
        response = client.post(
            "/api/ai-platform/sessions",
            json={
                "session_id": session_id,
                "user_id": "user-1",
                "workspace_id": "ws-123",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["session_id"] == session_id

    def test_add_message(self):
        """Test adding conversation message"""
        session_id = f"session-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/ai-platform/sessions",
            json={"session_id": session_id},
        )
        response = client.post(
            f"/api/ai-platform/sessions/{session_id}/messages",
            json={
                "session_id": session_id,
                "role": "user",
                "content": "Hello, how are you?",
                "tokens": 10,
            },
        )
        assert response.status_code == 201

    def test_get_history(self):
        """Test getting conversation history"""
        session_id = f"session-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/ai-platform/sessions",
            json={"session_id": session_id},
        )
        client.post(
            f"/api/ai-platform/sessions/{session_id}/messages",
            json={"session_id": session_id, "role": "user", "content": "Test"},
        )
        response = client.get(f"/api/ai-platform/sessions/{session_id}/history")
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data

    def test_get_context(self):
        """Test getting session context"""
        session_id = f"session-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/ai-platform/sessions",
            json={"session_id": session_id},
        )
        client.post(
            f"/api/ai-platform/sessions/{session_id}/messages",
            json={"session_id": session_id, "role": "user", "content": "Test"},
        )
        response = client.get(f"/api/ai-platform/sessions/{session_id}/context")
        assert response.status_code == 200
        data = response.json()
        assert "context" in data
