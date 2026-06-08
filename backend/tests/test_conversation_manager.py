"""Tests for conversation manager."""

import pytest
from app.api.conversation_manager import ConversationManager


@pytest.fixture
def manager():
    """Create fresh conversation manager instance."""
    return ConversationManager(max_turns=10)


def test_create_conversation(manager):
    """Test conversation creation."""
    conv_id = manager.create_conversation("client-1")

    assert conv_id is not None
    assert len(conv_id) == 12

    conv = manager.get_conversation(conv_id)
    assert conv is not None
    assert conv.client_id == "client-1"


def test_add_user_turn(manager):
    """Test adding user turn."""
    conv_id = manager.create_conversation("client-1")

    success = manager.add_user_turn(conv_id, "Hello")
    assert success is True

    conv = manager.get_conversation(conv_id)
    assert len(conv.turns) == 1
    assert conv.turns[0].role == "user"
    assert conv.turns[0].content == "Hello"


def test_add_assistant_turn(manager):
    """Test adding assistant turn."""
    conv_id = manager.create_conversation("client-1")
    manager.add_user_turn(conv_id, "Hello")

    success = manager.add_assistant_turn(conv_id, "Hi there!")
    assert success is True

    conv = manager.get_conversation(conv_id)
    assert len(conv.turns) == 2
    assert conv.turns[1].role == "assistant"
    assert conv.turns[1].content == "Hi there!"


def test_add_tool_call(manager):
    """Test adding tool call."""
    conv_id = manager.create_conversation("client-1")

    success = manager.add_tool_call(
        conv_id,
        tool_name="search",
        tool_args={"query": "RAG"},
        call_id="call-123",
    )
    assert success is True

    conv = manager.get_conversation(conv_id)
    assert len(conv.tool_calls) == 1
    assert conv.tool_calls[0].tool_name == "search"


def test_add_tool_result(manager):
    """Test adding tool result."""
    conv_id = manager.create_conversation("client-1")
    manager.add_tool_call(conv_id, "search", {"query": "RAG"}, "call-123")

    success = manager.add_tool_result(
        conv_id,
        call_id="call-123",
        result={"documents": ["doc1", "doc2"]},
        success=True,
    )
    assert success is True

    conv = manager.get_conversation(conv_id)
    assert len(conv.tool_results) == 1
    assert conv.tool_results[0].success is True


def test_get_context_messages(manager):
    """Test context message generation."""
    conv_id = manager.create_conversation("client-1")
    manager.add_user_turn(conv_id, "What is RAG?")
    manager.add_assistant_turn(conv_id, "RAG is retrieval-augmented generation.")

    messages = manager.get_context_messages(conv_id, system_prompt="You are helpful.")

    assert len(messages) == 3
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[2]["role"] == "assistant"


def test_prune_conversation(manager):
    """Test conversation pruning."""
    conv_id = manager.create_conversation("client-1")

    # Add 15 turns (exceeds max_turns=10)
    for i in range(15):
        manager.add_user_turn(conv_id, f"Turn {i}")

    conv = manager.get_conversation(conv_id)
    assert len(conv.turns) == 10  # Pruned to max_turns


def test_delete_conversation(manager):
    """Test conversation deletion."""
    conv_id = manager.create_conversation("client-1")

    success = manager.delete_conversation(conv_id)
    assert success is True

    conv = manager.get_conversation(conv_id)
    assert conv is None


def test_get_conversation_not_found(manager):
    """Test getting non-existent conversation."""
    conv = manager.get_conversation("non-existent-id")
    assert conv is None


def test_add_turn_to_nonexistent_conversation(manager):
    """Test adding turn to non-existent conversation."""
    success = manager.add_user_turn("non-existent-id", "Hello")
    assert success is False

    success = manager.add_assistant_turn("non-existent-id", "Hello")
    assert success is False


def test_add_tool_call_to_nonexistent_conversation(manager):
    """Test adding tool call to non-existent conversation."""
    success = manager.add_tool_call(
        "non-existent-id", "search", {}, "call-1"
    )
    assert success is False


def test_add_tool_result_to_nonexistent_conversation(manager):
    """Test adding tool result to non-existent conversation."""
    success = manager.add_tool_result(
        "non-existent-id", "call-1", {}, True
    )
    assert success is False


def test_delete_nonexistent_conversation(manager):
    """Test deleting non-existent conversation."""
    success = manager.delete_conversation("non-existent-id")
    assert success is False


def test_get_context_messages_nonexistent(manager):
    """Test getting context messages for non-existent conversation."""
    messages = manager.get_context_messages("non-existent-id")
    assert messages == []


def test_get_context_messages_without_system_prompt(manager):
    """Test context messages without system prompt."""
    conv_id = manager.create_conversation("client-1")
    manager.add_user_turn(conv_id, "Hello")
    manager.add_assistant_turn(conv_id, "Hi!")

    messages = manager.get_context_messages(conv_id)

    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


def test_conversation_stats(manager):
    """Test conversation statistics."""
    # Create two conversations with some turns
    conv1 = manager.create_conversation("client-1")
    manager.add_user_turn(conv1, "Hello")
    manager.add_assistant_turn(conv1, "Hi!")
    manager.add_user_turn(conv1, "How are you?")

    conv2 = manager.create_conversation("client-2")
    manager.add_user_turn(conv2, "Hey!")

    stats = manager.get_conversation_stats()

    assert stats["total_conversations"] == 2
    assert stats["total_turns"] == 4
    assert stats["total_tool_calls"] == 0
    assert stats["total_tool_results"] == 0


def test_tool_call_and_result_matching(manager):
    """Test tool call and result matching."""
    conv_id = manager.create_conversation("client-1")

    # Add multiple tool calls
    manager.add_tool_call(conv_id, "search", {"q": "1"}, "call-1")
    manager.add_tool_call(conv_id, "calculator", {"expr": "2+2"}, "call-2")

    # Add results
    manager.add_tool_result(conv_id, "call-1", {"docs": []}, True)
    manager.add_tool_result(conv_id, "call-2", {"result": 4}, True)

    conv = manager.get_conversation(conv_id)
    assert len(conv.tool_calls) == 2
    assert len(conv.tool_results) == 2
    assert conv.tool_results[0].call_id == "call-1"
    assert conv.tool_results[1].call_id == "call-2"


def test_tool_result_with_error(manager):
    """Test tool result with error."""
    conv_id = manager.create_conversation("client-1")
    manager.add_tool_call(conv_id, "failing_tool", {}, "call-1")

    manager.add_tool_result(
        conv_id, "call-1", {}, success=False, error="Tool execution failed"
    )

    conv = manager.get_conversation(conv_id)
    assert conv.tool_results[0].success is False
    assert conv.tool_results[0].error == "Tool execution failed"


def test_conversation_timestamps(manager):
    """Test that timestamps are set correctly."""
    conv_id = manager.create_conversation("client-1")
    conv = manager.get_conversation(conv_id)

    assert conv.created_at is not None
    assert conv.updated_at is not None
    assert conv.created_at <= conv.updated_at


def test_turn_timestamps(manager):
    """Test turn timestamps."""
    conv_id = manager.create_conversation("client-1")
    manager.add_user_turn(conv_id, "Hello")

    conv = manager.get_conversation(conv_id)
    assert conv.turns[0].timestamp is not None


def test_turn_metadata(manager):
    """Test turn metadata."""
    conv_id = manager.create_conversation("client-1")
    metadata = {"tokens": 100, "model": "gpt-4"}
    manager.add_user_turn(conv_id, "Hello", metadata=metadata)

    conv = manager.get_conversation(conv_id)
    assert conv.turns[0].metadata == metadata


def test_multiple_conversations(manager):
    """Test multiple concurrent conversations."""
    conv1 = manager.create_conversation("client-1")
    conv2 = manager.create_conversation("client-2")
    conv3 = manager.create_conversation("client-3")

    manager.add_user_turn(conv1, "Hello from client 1")
    manager.add_user_turn(conv2, "Hello from client 2")
    manager.add_user_turn(conv3, "Hello from client 3")

    assert len(manager.conversations) == 3

    assert manager.get_conversation(conv1).turns[0].content == "Hello from client 1"
    assert manager.get_conversation(conv2).turns[0].content == "Hello from client 2"
    assert manager.get_conversation(conv3).turns[0].content == "Hello from client 3"
