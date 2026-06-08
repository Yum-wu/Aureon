"""
Integration tests for WebSocket chat.

Tests:
- Connection lifecycle
- Multi-turn conversations
- Streaming responses
- Tool calling
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
import json

from app.api.websocket import WebSocketManager
from app.api.conversation_manager import ConversationManager


class TestWebSocketIntegration:
    """Integration test suite for WebSocket chat."""

    @pytest.fixture
    def managers(self):
        """Create fresh manager instances."""
        return WebSocketManager(), ConversationManager()

    @pytest.mark.asyncio
    async def test_full_conversation_flow(self, managers):
        """Test complete conversation flow."""
        ws_manager, conv_manager = managers

        # Create conversation
        conv_id = conv_manager.create_conversation("test-client")

        # Add user turn
        conv_manager.add_user_turn(conv_id, "What is RAG?")

        # Get context
        messages = conv_manager.get_context_messages(conv_id)
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

        # Add assistant turn
        conv_manager.add_assistant_turn(
            conv_id,
            "RAG is retrieval-augmented generation.",
            metadata={"sources": [{"title": "RAG Intro"}]},
        )

        # Verify conversation state
        conv = conv_manager.get_conversation(conv_id)
        assert len(conv.turns) == 2

    @pytest.mark.asyncio
    async def test_tool_calling_flow(self, managers):
        """Test tool calling flow."""
        ws_manager, conv_manager = managers

        conv_id = conv_manager.create_conversation("test-client")

        # Add user turn
        conv_manager.add_user_turn(conv_id, "Search for RAG articles")

        # Add tool call
        conv_manager.add_tool_call(
            conv_id,
            tool_name="search",
            tool_args={"query": "RAG"},
            call_id="call-123",
        )

        # Add tool result
        conv_manager.add_tool_result(
            conv_id,
            call_id="call-123",
            result={"documents": ["doc1", "doc2"]},
            success=True,
        )

        # Verify tool calls tracked
        conv = conv_manager.get_conversation(conv_id)
        assert len(conv.tool_calls) == 1
        assert len(conv.tool_results) == 1

    @pytest.mark.asyncio
    async def test_multi_turn_conversation(self, managers):
        """Test multi-turn conversation with context maintenance."""
        ws_manager, conv_manager = managers

        conv_id = conv_manager.create_conversation("test-client")

        # Turn 1: User asks about RAG
        conv_manager.add_user_turn(conv_id, "What is RAG?")
        conv_manager.add_assistant_turn(conv_id, "RAG is retrieval-augmented generation.")

        # Turn 2: User asks follow-up
        conv_manager.add_user_turn(conv_id, "How does it work?")
        conv_manager.add_assistant_turn(conv_id, "It retrieves relevant documents and uses them as context.")

        # Verify context contains all turns
        messages = conv_manager.get_context_messages(conv_id)
        assert len(messages) == 4  # 2 user + 2 assistant
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "user"
        assert messages[3]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_conversation_pruning(self, managers):
        """Test conversation pruning when exceeding max turns."""
        ws_manager, conv_manager = managers

        # Set low max turns
        conv_manager.max_turns = 4
        conv_id = conv_manager.create_conversation("test-client")

        # Add 6 turns (exceeds max)
        for i in range(6):
            conv_manager.add_user_turn(conv_id, f"User message {i}")
            conv_manager.add_assistant_turn(conv_id, f"Assistant message {i}")

        # Verify only recent turns are kept
        conv = conv_manager.get_conversation(conv_id)
        assert len(conv.turns) == 4
        assert conv.turns[0].content == "User message 4"
        assert conv.turns[3].content == "Assistant message 5"

    @pytest.mark.asyncio
    async def test_conversation_context_messages_with_system_prompt(self, managers):
        """Test context messages with optional system prompt."""
        ws_manager, conv_manager = managers

        conv_id = conv_manager.create_conversation("test-client")
        conv_manager.add_user_turn(conv_id, "Hello")

        # Get context with system prompt
        messages = conv_manager.get_context_messages(
            conv_id,
            system_prompt="You are a helpful assistant."
        )

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a helpful assistant."
        assert messages[1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_tool_call_error_handling(self, managers):
        """Test tool calling with error handling."""
        ws_manager, conv_manager = managers

        conv_id = conv_manager.create_conversation("test-client")
        conv_manager.add_user_turn(conv_id, "Run a failing tool")

        # Add tool call
        conv_manager.add_tool_call(
            conv_id,
            tool_name="failing_tool",
            tool_args={},
            call_id="call-456",
        )

        # Add failed tool result
        conv_manager.add_tool_result(
            conv_id,
            call_id="call-456",
            result=None,
            success=False,
            error="Tool execution failed",
        )

        conv = conv_manager.get_conversation(conv_id)
        assert len(conv.tool_results) == 1
        assert conv.tool_results[0].success is False
        assert conv.tool_results[0].error == "Tool execution failed"

    @pytest.mark.asyncio
    async def test_conversation_metadata_tracking(self, managers):
        """Test conversation metadata is properly tracked."""
        ws_manager, conv_manager = managers

        conv_id = conv_manager.create_conversation("test-client")

        # Add turns with metadata
        conv_manager.add_user_turn(
            conv_id,
            "Search query",
            metadata={"search_query": "RAG articles", "user_intent": "search"}
        )

        conv = conv_manager.get_conversation(conv_id)
        assert conv.turns[0].metadata["search_query"] == "RAG articles"
        assert conv.turns[0].metadata["user_intent"] == "search"

    @pytest.mark.asyncio
    async def test_conversation_stats(self, managers):
        """Test conversation statistics tracking."""
        ws_manager, conv_manager = managers

        # Create multiple conversations
        conv1_id = conv_manager.create_conversation("client-1")
        conv2_id = conv_manager.create_conversation("client-2")

        # Add turns
        conv_manager.add_user_turn(conv1_id, "Message 1")
        conv_manager.add_assistant_turn(conv1_id, "Response 1")
        conv_manager.add_user_turn(conv2_id, "Message 2")

        # Get stats
        stats = conv_manager.get_conversation_stats()

        assert stats["total_conversations"] == 2
        assert stats["total_turns"] == 3
        assert stats["avg_turns_per_conversation"] == 1.5

    @pytest.mark.asyncio
    async def test_conversation_deletion(self, managers):
        """Test conversation deletion."""
        ws_manager, conv_manager = managers

        conv_id = conv_manager.create_conversation("test-client")
        conv_manager.add_user_turn(conv_id, "Message to delete")

        # Delete conversation
        result = conv_manager.delete_conversation(conv_id)
        assert result is True

        # Verify it's deleted
        conv = conv_manager.get_conversation(conv_id)
        assert conv is None

    @pytest.mark.asyncio
    async def test_nonexistent_conversation(self, managers):
        """Test operations on nonexistent conversation."""
        ws_manager, conv_manager = managers

        # Try to add turn to nonexistent conversation
        result = conv_manager.add_user_turn("nonexistent", "Message")
        assert result is False

        # Try to get nonexistent conversation
        conv = conv_manager.get_conversation("nonexistent")
        assert conv is None

    @pytest.mark.asyncio
    async def test_websocket_connection_lifecycle(self, managers):
        """Test WebSocket connection lifecycle."""
        ws_manager, conv_manager = managers

        # Mock WebSocket
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.send_json = AsyncMock()

        # Connect
        await ws_manager.connect(mock_ws, "test-client")

        # Verify connection stored
        assert ws_manager.get_connection_count() == 1
        assert "test-client" in ws_manager.active_connections

        # Verify metadata stored
        info = ws_manager.get_connection_info()
        assert len(info) == 1
        assert info[0]["client_id"] == "test-client"

        # Disconnect
        await ws_manager.disconnect("test-client")

        # Verify cleanup
        assert ws_manager.get_connection_count() == 0
        mock_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_message_broadcast(self, managers):
        """Test WebSocket message broadcast to multiple clients."""
        ws_manager, conv_manager = managers

        # Create two mock WebSocket connections
        mock_ws1 = AsyncMock()
        mock_ws1.accept = AsyncMock()
        mock_ws2 = AsyncMock()
        mock_ws2.accept = AsyncMock()

        # Connect both clients
        await ws_manager.connect(mock_ws1, "client-1")
        await ws_manager.connect(mock_ws2, "client-2")

        # Broadcast message
        await ws_manager.broadcast({"type": "announcement", "message": "Hello"})

        # Verify both clients received the message
        assert mock_ws1.send_json.call_count == 1
        assert mock_ws2.send_json.call_count == 1

        # Verify message content
        call_args1 = mock_ws1.send_json.call_args[0][0]
        call_args2 = mock_ws2.send_json.call_args[0][0]
        assert call_args1["type"] == "announcement"
        assert call_args2["type"] == "announcement"

    @pytest.mark.asyncio
    async def test_websocket_send_json(self, managers):
        """Test WebSocket JSON message sending."""
        ws_manager, conv_manager = managers

        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        await ws_manager.connect(mock_ws, "test-client")

        # Send JSON message
        await ws_manager.send_json("test-client", {"type": "test", "data": "hello"})

        # Verify message sent
        mock_ws.send_json.assert_called_once_with({"type": "test", "data": "hello"})

        # Verify message count updated
        info = ws_manager.get_connection_info()
        assert info[0]["message_count"] == 1

    @pytest.mark.asyncio
    async def test_websocket_send_text(self, managers):
        """Test WebSocket raw text message sending."""
        ws_manager, conv_manager = managers

        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        await ws_manager.connect(mock_ws, "test-client")

        # Send text message
        await ws_manager.send_text("test-client", "Hello, world!")

        # Verify message sent
        mock_ws.send_text.assert_called_once_with("Hello, world!")

    @pytest.mark.asyncio
    async def test_websocket_send_to_disconnected_client(self, managers):
        """Test sending to disconnected client fails gracefully."""
        ws_manager, conv_manager = managers

        # Send to client that was never connected
        await ws_manager.send_json("nonexistent", {"type": "test"})

        # Should not raise, just log warning
        assert ws_manager.get_connection_count() == 0

    @pytest.mark.asyncio
    async def test_conversation_with_multiple_tool_calls(self, managers):
        """Test conversation with multiple tool calls."""
        ws_manager, conv_manager = managers

        conv_id = conv_manager.create_conversation("test-client")
        conv_manager.add_user_turn(conv_id, "Perform multiple searches")

        # Multiple tool calls
        conv_manager.add_tool_call(conv_id, "search1", {"query": "q1"}, "call-1")
        conv_manager.add_tool_call(conv_id, "search2", {"query": "q2"}, "call-2")
        conv_manager.add_tool_call(conv_id, "search3", {"query": "q3"}, "call-3")

        # Multiple tool results
        conv_manager.add_tool_result(conv_id, "call-1", {"results": []}, True)
        conv_manager.add_tool_result(conv_id, "call-2", {"results": []}, True)
        conv_manager.add_tool_result(conv_id, "call-3", {"results": []}, True)

        conv = conv_manager.get_conversation(conv_id)
        assert len(conv.tool_calls) == 3
        assert len(conv.tool_results) == 3

    @pytest.mark.asyncio
    async def test_heartbeat_tracking(self, managers):
        """Test heartbeat tracking in WebSocket manager."""
        ws_manager, conv_manager = managers

        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        await ws_manager.connect(mock_ws, "test-client")

        # Update heartbeat
        ws_manager.update_heartbeat("test-client")

        # Verify metadata updated
        info = ws_manager.get_connection_info()
        assert "last_heartbeat" in info[0]
