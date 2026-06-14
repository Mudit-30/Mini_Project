"""
gridmind_server.app.websockets
--------------------------------
Real-time WebSocket manager for broadcasting node telemetry and task
events to all connected dashboard clients.

Design notes
------------
- Stale connections are collected *after* the broadcast loop so the list
  is never mutated while being iterated.
- ``default=str`` in json.dumps handles datetime objects gracefully.
- Connections list is a plain list; lock is not needed because FastAPI /
  asyncio is single-threaded for async code.
"""
from __future__ import annotations

import json
import logging
from typing import List

from fastapi import WebSocket

logger = logging.getLogger("gridmind.websockets")


class ConnectionManager:
    """Manages a pool of active WebSocket connections."""

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            "Dashboard client connected. Active connections: %d",
            len(self.active_connections),
        )

    def disconnect(self, websocket: WebSocket) -> None:
        try:
            self.active_connections.remove(websocket)
            logger.info(
                "Dashboard client disconnected. Active connections: %d",
                len(self.active_connections),
            )
        except ValueError:
            pass  # already removed

    async def broadcast(self, message: dict) -> None:
        """
        Serialize *message* as JSON and push to every connected client.
        Stale/dead connections are quietly removed.
        """
        if not self.active_connections:
            return

        payload = json.dumps(message, default=str)
        dead: list[WebSocket] = []

        for ws in list(self.active_connections):  # snapshot to allow safe removal
            try:
                await ws.send_text(payload)
            except Exception as exc:
                logger.warning("WebSocket send failed (%s) — removing client.", exc)
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws)


# Module-level singleton — imported by grpc_server, dispatcher_loop, main
manager = ConnectionManager()
