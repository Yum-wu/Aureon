"""WebSocket connection manager for real-time chat."""

import os
from typing import Dict, Any, Optional, List
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
import json
import asyncio
import structlog

logger = structlog.get_logger()


class WebSocketManager:
    """WebSocket connection manager.

    Manages:
    - Client connections and disconnections
    - Message routing and serialization
    - Connection pooling and cleanup
    - Heartbeat monitoring

    Supports:
    - Multi-turn conversations
    - Streaming responses (token-by-token)
    - Tool calling orchestration
    - Error handling and recovery
    """

    def __init__(self):
        """Initialize WebSocket manager."""
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._max_connections = int(os.getenv("WEBSOCKET_MAX_CONNECTIONS", "300"))
        self._connection_order: list = []

    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept WebSocket connection and register client.

        If at capacity, evicts the oldest idle connection.
        """
        # Evict oldest if at capacity
        if len(self.active_connections) >= self._max_connections and client_id not in self.active_connections:
            if self._connection_order:
                oldest_id = self._connection_order.pop(0)
                await self._evict_client(oldest_id)

        try:
            await websocket.accept()
            self.active_connections[client_id] = websocket
            self.connection_metadata[client_id] = {
                "connected_at": datetime.now(),
                "last_heartbeat": datetime.now(),
                "message_count": 0,
                "conversation_id": None,
            }
            if client_id not in self._connection_order:
                self._connection_order.append(client_id)
            logger.info(
                "Client connected",
                client_id=client_id,
                total_connections=len(self.active_connections),
            )
        except Exception as e:
            logger.error("Connection failed", client_id=client_id, error=str(e))
            raise

    async def _evict_client(self, client_id: str):
        """Gracefully close and remove a client connection."""
        ws = self.active_connections.get(client_id)
        if ws:
            try:
                await ws.send_json({"type": "error", "message": "Connection evicted: server at capacity"})
                await ws.close(code=1013, reason="Server full")
            except Exception:
                pass
        self.active_connections.pop(client_id, None)
        self.connection_metadata.pop(client_id, None)
        logger.info("Client evicted", client_id=client_id)

    async def disconnect(self, client_id: str):
        """Disconnect client and cleanup resources."""
        if client_id in self.active_connections:
            try:
                websocket = self.active_connections[client_id]
                await websocket.close()
                del self.active_connections[client_id]
                del self.connection_metadata[client_id]
                if client_id in self._connection_order:
                    self._connection_order.remove(client_id)
                logger.info(
                    "Client disconnected",
                    client_id=client_id,
                    remaining_connections=len(self.active_connections),
                )
            except Exception as e:
                logger.warning(
                    "Error during disconnect",
                    client_id=client_id,
                    error=str(e),
                )
                # Cleanup even if close fails
                if client_id in self.active_connections:
                    del self.active_connections[client_id]
                if client_id in self.connection_metadata:
                    del self.connection_metadata[client_id]
                if client_id in self._connection_order:
                    self._connection_order.remove(client_id)
        else:
            logger.debug(
                "Client already disconnected",
                client_id=client_id,
            )

    async def send_json(self, client_id: str, data: Dict[str, Any]):
        """Send JSON message to client."""
        if client_id not in self.active_connections:
            logger.warning(
                "Cannot send to disconnected client",
                client_id=client_id,
            )
            return

        try:
            websocket = self.active_connections[client_id]
            await websocket.send_json(data)
            self.connection_metadata[client_id]["message_count"] += 1
            logger.debug(
                "Sent JSON message",
                client_id=client_id,
                message_type=data.get("type"),
            )
        except WebSocketDisconnect:
            logger.warning(
                "Client disconnected during send",
                client_id=client_id,
            )
            await self.disconnect(client_id)
        except Exception as e:
            logger.error(
                "Error sending JSON message",
                client_id=client_id,
                error=str(e),
            )

    async def send_text(self, client_id: str, text: str):
        """Send raw text message to client."""
        if client_id not in self.active_connections:
            logger.warning(
                "Cannot send to disconnected client",
                client_id=client_id,
            )
            return

        try:
            websocket = self.active_connections[client_id]
            await websocket.send_text(text)
            self.connection_metadata[client_id]["message_count"] += 1
            logger.debug(
                "Sent text message",
                client_id=client_id,
                length=len(text),
            )
        except WebSocketDisconnect:
            logger.warning(
                "Client disconnected during send",
                client_id=client_id,
            )
            await self.disconnect(client_id)
        except Exception as e:
            logger.error(
                "Error sending text message",
                client_id=client_id,
                error=str(e),
            )

    async def broadcast(
        self, data: Dict[str, Any], exclude_client: Optional[str] = None
    ):
        """Broadcast message to all connected clients."""
        disconnected_clients = []

        for client_id, websocket in self.active_connections.items():
            if client_id == exclude_client:
                continue

            try:
                await websocket.send_json(data)
                self.connection_metadata[client_id]["message_count"] += 1
            except WebSocketDisconnect:
                disconnected_clients.append(client_id)
            except Exception as e:
                logger.error(
                    "Error broadcasting to client",
                    client_id=client_id,
                    error=str(e),
                )
                disconnected_clients.append(client_id)

        # Cleanup disconnected clients
        for client_id in disconnected_clients:
            await self.disconnect(client_id)

        logger.debug(
            "Broadcast complete",
            total_sent=len(self.active_connections) - len(disconnected_clients),
            failed=len(disconnected_clients),
        )

    async def start_heartbeat_monitor(self):
        """Start heartbeat monitoring background task."""
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_monitor())
            logger.info("Heartbeat monitor started")

    async def stop_heartbeat_monitor(self):
        """Stop heartbeat monitoring background task."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            logger.info("Heartbeat monitor stopped")

    async def _heartbeat_monitor(self):
        """Monitor client heartbeats and cleanup stale connections."""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds

                now = datetime.now()
                stale_clients = []

                for client_id, metadata in self.connection_metadata.items():
                    last_heartbeat = metadata.get("last_heartbeat", now)
                    time_since_heartbeat = (now - last_heartbeat).total_seconds()

                    # Disconnect if no heartbeat for 60 seconds
                    if time_since_heartbeat > 60:
                        stale_clients.append(client_id)

                for client_id in stale_clients:
                    logger.warning(
                        "Stale connection detected",
                        client_id=client_id,
                        seconds_since_heartbeat=(
                            now - self.connection_metadata[client_id]["last_heartbeat"]
                        ).total_seconds()
                        if client_id in self.connection_metadata
                        else 0,
                    )
                    await self.disconnect(client_id)

                if stale_clients:
                    logger.info(
                        "Cleaned up stale connections",
                        count=len(stale_clients),
                        remaining=len(self.active_connections),
                    )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(
                    "Error in heartbeat monitor",
                    error=str(e),
                )
                await asyncio.sleep(5)  # Brief pause before retry

    def update_heartbeat(self, client_id: str):
        """Update client heartbeat timestamp."""
        if client_id in self.connection_metadata:
            self.connection_metadata[client_id]["last_heartbeat"] = datetime.now()

    def set_conversation_id(self, client_id: str, conversation_id: str):
        """Set conversation ID for client."""
        if client_id in self.connection_metadata:
            self.connection_metadata[client_id]["conversation_id"] = conversation_id

    def get_connection_count(self) -> int:
        """Get number of active connections."""
        return len(self.active_connections)

    def get_connection_info(self) -> List[Dict[str, Any]]:
        """Get information about all active connections."""
        info = []
        for client_id, metadata in self.connection_metadata.items():
            info.append(
                {
                    "client_id": client_id,
                    "connected_at": metadata.get("connected_at"),
                    "last_heartbeat": metadata.get("last_heartbeat"),
                    "message_count": metadata.get("message_count", 0),
                    "conversation_id": metadata.get("conversation_id"),
                }
            )
        return info
