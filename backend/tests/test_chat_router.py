"""Tests for Chat router (POST /api/chat/stream, /api/chat/enhanced/stream,
GET /api/sessions, DELETE /api/sessions/{session_id})."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_chat_stream_returns_sse():
    """POST /api/chat/stream returns SSE with text/event-stream content type."""

    async def fake_stream():
        yield "data: hello\n\n"
        yield "data: world\n\n"

    mock_agent = MagicMock()

    with patch("app.routers.chat._get_agent", new_callable=AsyncMock, return_value=mock_agent), \
         patch("app.routers.chat.stream_agent_with_memory", return_value=fake_stream()), \
         patch("app.routers.chat.memory_manager"):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/chat/stream",
                json={"message": "hello", "session_id": "test-session"},
            )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert "hello" in body
    assert "world" in body


@pytest.mark.asyncio
async def test_chat_enhanced_stream_returns_sse():
    """POST /api/chat/enhanced/stream returns SSE events."""

    async def fake_workflow(**kwargs):
        yield {"type": "text", "content": "enhanced"}
        yield {"type": "done"}

    with patch("app.langgraph.streaming.stream_workflow", side_effect=lambda **kw: fake_workflow(**kw)), \
         patch("app.routers.chat.create_llm", return_value=MagicMock()):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/chat/enhanced/stream",
                json={"message": "tell me about AI", "session_id": "test-session"},
            )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "enhanced" in resp.text


@pytest.mark.asyncio
async def test_list_sessions():
    """GET /api/sessions returns session list with count."""
    mock_sessions = ["sess-1", "sess-2", "sess-3"]

    with patch("app.routers.chat.memory_manager") as mock_mm:
        mock_mm.get_active_sessions.return_value = mock_sessions
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/chat/sessions")

    assert resp.status_code == 200
    data = resp.json()
    assert data["sessions"] == mock_sessions
    assert data["count"] == 3


@pytest.mark.asyncio
async def test_delete_session():
    """DELETE /api/sessions/{session_id} deletes and returns status."""
    with patch("app.routers.chat.memory_manager") as mock_mm:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.delete("/api/chat/sessions/sess-to-delete")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deleted"
    assert data["session_id"] == "sess-to-delete"
    mock_mm.finalize_scenario.assert_called_once_with(
        "sess-to-delete", "用户手动清除会话"
    )
    mock_mm.clear_session.assert_called_once_with("sess-to-delete")
