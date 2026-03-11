"""
gridmind_server.app.websockets
--------------------------------
Real-time WebSocket manager for broadcasting node telemetry to the dashboard.
"""
import json
import logging
from typing import List
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("gridmind.websockets")

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("New dashboard client connected. Total: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("Dashboard client disconnected. Total: %d", len(self.active_connections))

    async def broadcast(self, message: dict):
        """Send a JSON message to all connected clients."""
        if not self.active_connections:
            return

        payload = json.dumps(message)
        disconnected = []
        
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception as exc:
                logger.warning("Failed to send to client: %s", exc)
                disconnected.append(connection)
        
        # Clean up failed connections
        for conn in disconnected:
            self.disconnect(conn)

# Singleton manager
manager = ConnectionManager()
