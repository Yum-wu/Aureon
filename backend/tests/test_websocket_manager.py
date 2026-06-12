"""Tests for WebSocket connection manager."""

import pytest
from unittest.mock import AsyncMock
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect

from app.api.websocket import WebSocketManager


@pytest.fixture
def manager():
    """Create fresh WebSocket manager instance."""
    return WebSocketManager()


@pytest.fixture
def mock_websocket():
    """Create mock WebSocket connection."""
    ws = AsyncMock(spec=WebSocket)
    ws.send_json = AsyncMock()
    ws.send_text = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def mock_websocket_with_disconnect():
    """Create mock WebSocket that raises disconnect on send."""
    ws = AsyncMock(spec=WebSocket)
    ws.send_json = AsyncMock(side_effect=WebSocketDisconnect)
    ws.send_text = AsyncMock(side_effect=WebSocketDisconnect)
    ws.close = AsyncMock()
    return ws


def test_initialization(manager):
    """Test manager initializes correctly."""
    assert manager.active_connections == {}
    assert manager.connection_metadata == {}
    assert manager.get_connection_count() == 0


@pytest.mark.asyncio
async def test_connect(manager, mock_websocket):
    """Test client connection."""
    await manager.connect(mock_websocket, "client-1")

    assert "client-1" in manager.active_connections
    assert manager.active_connections["client-1"] == mock_websocket
    assert manager.get_connection_count() == 1
    mock_websocket.accept.assert_called_once()


@pytest.mark.asyncio
async def test_connect_multiple_clients(manager):
    """Test multiple client connections."""
    ws1 = AsyncMock(spec=WebSocket)
    ws1.send_json = AsyncMock()
    ws2 = AsyncMock(spec=WebSocket)
    ws2.send_json = AsyncMock()

    await manager.connect(ws1, "client-1")
    await manager.connect(ws2, "client-2")

    assert manager.get_connection_count() == 2
    assert "client-1" in manager.active_connections
    assert "client-2" in manager.active_connections


@pytest.mark.asyncio
async def test_disconnect(manager, mock_websocket):
    """Test client disconnection."""
    await manager.connect(mock_websocket, "client-1")
    await manager.disconnect("client-1")

    assert "client-1" not in manager.active_connections
    assert "client-1" not in manager.connection_metadata
    assert manager.get_connection_count() == 0
    mock_websocket.close.assert_called_once()


@pytest.mark.asyncio
async def test_disconnect_nonexistent_client(manager):
    """Test disconnecting non-existent client doesn't raise error."""
    await manager.disconnect("nonexistent-client")
    assert manager.get_connection_count() == 0


@pytest.mark.asyncio
async def test_send_json(manager, mock_websocket):
    """Test sending JSON message."""
    await manager.connect(mock_websocket, "client-1")

    data = {"type": "text", "content": "Hello"}
    await manager.send_json("client-1", data)

    mock_websocket.send_json.assert_called_once_with(data)
    assert manager.connection_metadata["client-1"]["message_count"] == 1


@pytest.mark.asyncio
async def test_send_json_to_disconnected_client(manager):
    """Test sending JSON to disconnected client doesn't raise error."""
    data = {"type": "text", "content": "Hello"}
    await manager.send_json("nonexistent-client", data)


@pytest.mark.asyncio
async def test_send_json_handles_disconnect(manager, mock_websocket_with_disconnect):
    """Test send_json handles WebSocketDisconnect gracefully."""
    await manager.connect(mock_websocket_with_disconnect, "client-1")

    data = {"type": "text", "content": "Hello"}
    await manager.send_json("client-1", data)

    # Client should be disconnected after error
    assert "client-1" not in manager.active_connections


@pytest.mark.asyncio
async def test_send_text(manager, mock_websocket):
    """Test sending text message."""
    await manager.connect(mock_websocket, "client-1")

    text = "Hello, world!"
    await manager.send_text("client-1", text)

    mock_websocket.send_text.assert_called_once_with(text)
    assert manager.connection_metadata["client-1"]["message_count"] == 1


@pytest.mark.asyncio
async def test_send_text_to_disconnected_client(manager):
    """Test sending text to disconnected client doesn't raise error."""
    await manager.send_text("nonexistent-client", "Hello")


@pytest.mark.asyncio
async def test_send_text_handles_disconnect(manager, mock_websocket_with_disconnect):
    """Test send_text handles WebSocketDisconnect gracefully."""
    await manager.connect(mock_websocket_with_disconnect, "client-1")

    await manager.send_text("client-1", "Hello")

    # Client should be disconnected after error
    assert "client-1" not in manager.active_connections


@pytest.mark.asyncio
async def test_broadcast(manager):
    """Test broadcast message to all clients."""
    ws1 = AsyncMock(spec=WebSocket)
    ws1.send_json = AsyncMock()
    ws2 = AsyncMock(spec=WebSocket)
    ws2.send_json = AsyncMock()

    await manager.connect(ws1, "client-1")
    await manager.connect(ws2, "client-2")

    data = {"type": "announcement", "content": "Hello everyone"}
    await manager.broadcast(data)

    ws1.send_json.assert_called_once_with(data)
    ws2.send_json.assert_called_once_with(data)
    assert manager.connection_metadata["client-1"]["message_count"] == 1
    assert manager.connection_metadata["client-2"]["message_count"] == 1


@pytest.mark.asyncio
async def test_broadcast_with_exclusion(manager):
    """Test broadcast excludes specified client."""
    ws1 = AsyncMock(spec=WebSocket)
    ws1.send_json = AsyncMock()
    ws2 = AsyncMock(spec=WebSocket)
    ws2.send_json = AsyncMock()

    await manager.connect(ws1, "client-1")
    await manager.connect(ws2, "client-2")

    data = {"type": "message", "content": "Hello"}
    await manager.broadcast(data, exclude_client="client-1")

    ws1.send_json.assert_not_called()
    ws2.send_json.assert_called_once_with(data)


@pytest.mark.asyncio
async def test_broadcast_handles_disconnect(manager):
    """Test broadcast handles disconnect errors gracefully."""
    ws1 = AsyncMock(spec=WebSocket)
    ws1.send_json = AsyncMock(side_effect=WebSocketDisconnect)
    ws2 = AsyncMock(spec=WebSocket)
    ws2.send_json = AsyncMock()

    await manager.connect(ws1, "client-1")
    await manager.connect(ws2, "client-2")

    data = {"type": "message", "content": "Hello"}
    await manager.broadcast(data)

    # client-1 should be disconnected, client-2 should still be connected
    assert "client-1" not in manager.active_connections
    assert "client-2" in manager.active_connections


def test_update_heartbeat(manager):
    """Test heartbeat update."""
    manager.connection_metadata["client-1"] = {
        "last_heartbeat": datetime.min,
    }

    manager.update_heartbeat("client-1")

    assert manager.connection_metadata["client-1"]["last_heartbeat"] > datetime.min


def test_update_heartbeat_nonexistent_client(manager):
    """Test heartbeat update for non-existent client doesn't raise error."""
    manager.update_heartbeat("nonexistent-client")


def test_set_conversation_id(manager):
    """Test setting conversation ID."""
    manager.connection_metadata["client-1"] = {"conversation_id": None}

    manager.set_conversation_id("client-1", "conv-123")

    assert manager.connection_metadata["client-1"]["conversation_id"] == "conv-123"


def test_set_conversation_id_nonexistent_client(manager):
    """Test setting conversation ID for non-existent client doesn't raise error."""
    manager.set_conversation_id("nonexistent-client", "conv-123")


def test_get_connection_info(manager):
    """Test connection info retrieval."""
    manager.connection_metadata["client-1"] = {
        "connected_at": datetime.now(),
        "last_heartbeat": datetime.now(),
        "message_count": 5,
        "conversation_id": "conv-123",
    }

    info = manager.get_connection_info()

    assert len(info) == 1
    assert info[0]["client_id"] == "client-1"
    assert info[0]["message_count"] == 5
    assert info[0]["conversation_id"] == "conv-123"


def test_get_connection_info_empty(manager):
    """Test connection info when no connections."""
    info = manager.get_connection_info()
    assert info == []


def test_get_connection_info_multiple_clients(manager):
    """Test connection info for multiple clients."""
    now = datetime.now()
    manager.connection_metadata["client-1"] = {
        "connected_at": now,
        "last_heartbeat": now,
        "message_count": 3,
        "conversation_id": "conv-1",
    }
    manager.connection_metadata["client-2"] = {
        "connected_at": now,
        "last_heartbeat": now,
        "message_count": 7,
        "conversation_id": "conv-2",
    }

    info = manager.get_connection_info()

    assert len(info) == 2
    client_ids = {i["client_id"] for i in info}
    assert client_ids == {"client-1", "client-2"}


@pytest.mark.asyncio
async def test_connect_increments_message_count(manager, mock_websocket):
    """Test that message count increments on send."""
    await manager.connect(mock_websocket, "client-1")

    await manager.send_json("client-1", {"type": "message"})
    await manager.send_json("client-1", {"type": "message"})
    await manager.send_text("client-1", "text")

    assert manager.connection_metadata["client-1"]["message_count"] == 3


@pytest.mark.asyncio
async def test_disconnect_preserves_other_connections(manager):
    """Test disconnecting one client preserves others."""
    ws1 = AsyncMock(spec=WebSocket)
    ws1.send_json = AsyncMock()
    ws2 = AsyncMock(spec=WebSocket)
    ws2.send_json = AsyncMock()

    await manager.connect(ws1, "client-1")
    await manager.connect(ws2, "client-2")

    await manager.disconnect("client-1")

    assert "client-1" not in manager.active_connections
    assert "client-2" in manager.active_connections
    assert manager.get_connection_count() == 1
