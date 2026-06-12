"""Tests for WebSocket chat endpoint."""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import WebSocket, WebSocketDisconnect

from app.api.websocket_chat import websocket_chat


async def _empty_async_iter():
    """Helper: async generator that yields nothing."""
    if False:
        yield


@pytest.fixture
def mock_websocket():
    """Create mock WebSocket connection."""
    ws = AsyncMock(spec=WebSocket)
    ws.receive_json = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def mock_websocket_disconnect():
    """Create mock WebSocket that raises disconnect on receive."""
    ws = AsyncMock(spec=WebSocket)
    ws.receive_json = AsyncMock(side_effect=WebSocketDisconnect())
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


class TestWebSocketChat:
    """Test suite for WebSocket chat endpoint."""

    @pytest.mark.asyncio
    async def test_connection_established(self, mock_websocket_disconnect):
        """Test WebSocket connection establishment.

        WebSocketDisconnect is now caught internally, so we just verify
        the welcome message was sent before the disconnect.
        """
        await websocket_chat(mock_websocket_disconnect, "client-1")

        # Should have sent welcome message
        mock_websocket_disconnect.send_json.assert_called()
        call_args = mock_websocket_disconnect.send_json.call_args[0]
        data = json.loads(call_args[0]) if isinstance(call_args[0], str) else call_args[0]
        assert data.get("type") == "connected"
        assert "conversation_id" in data
        assert data.get("message") == "Connected to Aureon chat"

    @pytest.mark.asyncio
    async def test_heartbeat_handling(self, mock_websocket):
        """Test heartbeat message handling."""
        # First message: heartbeat, then disconnect
        mock_websocket.receive_json.side_effect = [
            {"type": "heartbeat"},
            WebSocketDisconnect(),
        ]

        await websocket_chat(mock_websocket, "client-1")

        # Should have sent heartbeat_ack
        assert mock_websocket.send_json.call_count >= 2
        # Verify heartbeat_ack was sent
        calls = [call[0][0] for call in mock_websocket.send_json.call_args_list]
        ack_calls = [call for call in calls if isinstance(call, dict) and call.get("type") == "heartbeat_ack"]
        assert len(ack_calls) >= 1

    @pytest.mark.asyncio
    async def test_user_message_empty(self, mock_websocket):
        """Test user message with empty query."""
        mock_websocket.receive_json.side_effect = [
            {"type": "user_message", "query": ""},
            WebSocketDisconnect(),
        ]

        await websocket_chat(mock_websocket, "client-1")

        # Should have sent error message
        calls = [call[0][0] for call in mock_websocket.send_json.call_args_list]
        error_calls = [call for call in calls if isinstance(call, dict) and call.get("type") == "error"]
        assert len(error_calls) >= 1

    @pytest.mark.asyncio
    async def test_unknown_message_type(self, mock_websocket):
        """Test handling of unknown message types."""
        mock_websocket.receive_json.side_effect = [
            {"type": "unknown_type", "data": "test"},
            WebSocketDisconnect(),
        ]

        await websocket_chat(mock_websocket, "client-1")

        # Should handle gracefully without error
        assert mock_websocket.send_json.call_count >= 1

    @pytest.mark.asyncio
    async def test_websocket_error_sends_error_message(self, mock_websocket):
        """Test that exceptions are caught and error message is sent.

        The error message sent to the client should NOT contain the raw
        exception message (to avoid leaking internal details), but it MUST
        be a structured error message with type='error'.
        """
        mock_websocket.receive_json.side_effect = [
            {"type": "user_message", "query": "test"},
            Exception("Test error"),
        ]

        # Mock the RAG pipeline so the user_message doesn't fail with embeddings error
        with patch("app.rag.qa_chain.rag_query_astream", return_value=_empty_async_iter()), \
             patch("app.agent.llm.create_llm", return_value=MagicMock()):
            await websocket_chat(mock_websocket, "client-1")

        # Should have sent error message
        calls = [call[0][0] for call in mock_websocket.send_json.call_args_list]
        error_calls = [call for call in calls if isinstance(call, dict) and call.get("type") == "error"]
        assert len(error_calls) >= 1
        # Internal exception message should NOT leak to client
        assert "Test error" not in error_calls[-1].get("message", "")
        # But it SHOULD have a generic user-facing error message
        assert len(error_calls[-1].get("message", "")) > 0

    @pytest.mark.asyncio
    async def test_tool_result_handling(self, mock_websocket):
        """Test tool result message handling."""
        mock_websocket.receive_json.side_effect = [
            {
                "type": "tool_result",
                "call_id": "call-123",
                "result": {"status": "success"},
                "success": True,
            },
            WebSocketDisconnect(),
        ]

        await websocket_chat(mock_websocket, "client-1")

        # Should have sent tool_result_ack
        calls = [call[0][0] for call in mock_websocket.send_json.call_args_list]
        ack_calls = [call for call in calls if isinstance(call, dict) and call.get("type") == "tool_result_ack"]
        assert len(ack_calls) >= 1

    @pytest.mark.asyncio
    async def test_tool_result_with_error(self, mock_websocket):
        """Test tool result with error."""
        mock_websocket.receive_json.side_effect = [
            {
                "type": "tool_result",
                "call_id": "call-456",
                "result": None,
                "success": False,
                "error": "Tool execution failed",
            },
            WebSocketDisconnect(),
        ]

        await websocket_chat(mock_websocket, "client-1")

        # Should have sent tool_result_ack
        calls = [call[0][0] for call in mock_websocket.send_json.call_args_list]
        ack_calls = [call for call in calls if isinstance(call, dict) and call.get("type") == "tool_result_ack"]
        assert len(ack_calls) >= 1

    @pytest.mark.asyncio
    async def test_conversation_created(self, mock_websocket_disconnect):
        """Test that conversation is created on connection."""
        await websocket_chat(mock_websocket_disconnect, "client-1")

        # Verify welcome message contains conversation_id
        call_args = mock_websocket_disconnect.send_json.call_args[0]
        data = json.loads(call_args[0]) if isinstance(call_args[0], str) else call_args[0]
        assert "conversation_id" in data
        assert data["conversation_id"] is not None
        assert len(data["conversation_id"]) > 0

    @pytest.mark.asyncio
    async def test_multiple_messages_sequence(self, mock_websocket):
        """Test handling multiple messages in sequence."""
        mock_websocket.receive_json.side_effect = [
            {"type": "heartbeat"},
            {"type": "user_message", "query": "What is RAG?"},
            WebSocketDisconnect(),
        ]

        # Mock the RAG pipeline so user_message doesn't fail
        with patch("app.rag.qa_chain.rag_query_astream", return_value=_empty_async_iter()), \
             patch("app.agent.llm.create_llm", return_value=MagicMock()):
            await websocket_chat(mock_websocket, "client-1")

        # Should have received at least 3 messages (welcome + heartbeat_ack + response messages)
        assert mock_websocket.send_json.call_count >= 3

    @pytest.mark.asyncio
    async def test_user_message_without_metadata(self, mock_websocket):
        """Test user message without optional metadata."""
        mock_websocket.receive_json.side_effect = [
            {"type": "user_message", "query": "test query"},
            WebSocketDisconnect(),
        ]

        # Mock the RAG pipeline so user_message doesn't fail
        with patch("app.rag.qa_chain.rag_query_astream", return_value=_empty_async_iter()), \
             patch("app.agent.llm.create_llm", return_value=MagicMock()):
            await websocket_chat(mock_websocket, "client-1")

        # Should handle gracefully
        assert mock_websocket.send_json.call_count >= 2


class TestWebSocketChatIntegration:
    """Integration tests for WebSocket chat endpoint."""

    @pytest.mark.asyncio
    async def test_rag_response_streaming(self, mock_websocket):
        """Test RAG response streaming (with mocked RAG)."""
        async def fake_rag_stream(*args, **kwargs):
            yield {"type": "sources", "sources": [{"title": "Test Doc"}]}
            yield {"type": "text", "content": "Hello"}
            yield {"type": "text", "content": " World"}

        with patch("app.rag.qa_chain.rag_query_astream", side_effect=fake_rag_stream):

            mock_websocket.receive_json.side_effect = [
                {"type": "user_message", "query": "test"},
                WebSocketDisconnect(),
            ]

            with patch("app.agent.llm.create_llm", return_value=MagicMock()):
                await websocket_chat(mock_websocket, "client-1")

            # Should have sent sources and text chunks
            calls = [call[0][0] for call in mock_websocket.send_json.call_args_list]
            source_calls = [call for call in calls if isinstance(call, dict) and call.get("type") == "sources"]
            text_calls = [call for call in calls if isinstance(call, dict) and call.get("type") == "text"]
            assert len(source_calls) >= 1
            assert len(text_calls) >= 2
