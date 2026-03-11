"""
gridmind_server.app.grpc_server
---------------------------------
Receives client-streaming TelemetryData messages from Node Agents.

For every received packet the servicer:
  1. Calls the Observer AI to classify the node's current state.
  2. Updates the in-memory NodeRegistry (for fast REST lookups).
  3. Persists a TelemetryRecord row to SQLite (async, non-blocking).
"""
from __future__ import annotations

import asyncio
import datetime
import logging

import grpc
import grpc.aio

from app import telemetry_pb2, telemetry_pb2_grpc
from app.db.database import AsyncSessionLocal, TelemetryRecord
from app.registry import node_registry
from app.websockets import manager as ws_manager

logger = logging.getLogger("gridmind.grpc")

GRPC_LISTEN_ADDR = "[::]:50051"

# Placeholder carbon value used until WattTime API is integrated
_DEFAULT_CARBON = 0.0


class TelemetryServicer(telemetry_pb2_grpc.TelemetryServiceServicer):
    """
    Handles persistent streaming connections from one or more Node Agents.

    Parameters
    ----------
    observer :
        Loaded ``ObserverInference`` singleton (injected at construction time).
    """

    def __init__(self, observer) -> None:
        self._observer = observer

    # ── helpers ────────────────────────────────────────────────────────────────
    async def _persist(self, record: TelemetryRecord) -> None:
        """Write a TelemetryRecord to SQLite in a non-blocking async task."""
        try:
            async with AsyncSessionLocal() as session:
                session.add(record)
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error("DB persist failed: %s", exc)

    # ── gRPC handler ───────────────────────────────────────────────────────────
    async def StreamTelemetry(
        self,
        request_iterator: grpc.aio.ServicerContext,
        context: grpc.aio.ServicerContext,
    ) -> telemetry_pb2.TelemetryResponse:
        node_id = "unknown"
        packets = 0
        try:
            async for data in request_iterator:
                node_id = data.node_id
                packets += 1

                # ── 1. Build feature snapshot for Observer AI ─────────────────
                snapshot = {
                    "cpu_usage_pct":        data.cpu_usage_pct,
                    "ram_usage_pct":        data.ram_usage_pct,
                    "kb_events_per_min":    data.kb_events_per_min,
                    "mouse_events_per_min": data.mouse_events_per_min,
                    "net_io_bytes":         float(data.net_io_bytes),
                    "process_count":        data.process_count,
                    "carbon_intensity_gco2": _DEFAULT_CARBON,
                }

                # ── 2. Observer AI prediction ─────────────────────────────────
                try:
                    prediction = self._observer.predict(snapshot)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Observer predict failed for [%s]: %s", node_id, exc)
                    prediction = {"label": -1, "state": "unknown", "confidence": 0.0}

                # ── 3. Update node registry (in-memory, instant) ──────────────
                node_registry.update(node_id, snapshot, prediction)

                # ── 3.1 Broadcast to WebSocket clients ────────────────────────
                asyncio.create_task(ws_manager.broadcast({
                    "type": "node_update",
                    "node": node_registry.get(node_id)
                }))

                logger.debug(
                    "[%s] state=%-14s conf=%.2f | CPU=%.1f%% RAM=%.1f%%",
                    node_id,
                    prediction["state"],
                    prediction["confidence"],
                    data.cpu_usage_pct,
                    data.ram_usage_pct,
                )

                # ── 4. Persist to SQLite (fire-and-forget) ────────────────────
                record = TelemetryRecord(
                    recorded_at           = datetime.datetime.now(datetime.timezone.utc),
                    node_id               = node_id,
                    cpu_usage_pct         = data.cpu_usage_pct,
                    ram_usage_pct         = data.ram_usage_pct,
                    kb_events_per_min     = data.kb_events_per_min,
                    mouse_events_per_min  = data.mouse_events_per_min,
                    net_io_bytes          = data.net_io_bytes,
                    process_count         = data.process_count,
                    carbon_intensity_gco2 = _DEFAULT_CARBON,
                    predicted_label       = prediction["label"],
                    predicted_state       = prediction["state"],
                    prediction_confidence = prediction["confidence"],
                )
                asyncio.create_task(self._persist(record))

            # Client disconnected cleanly
            logger.info("Node [%s] disconnected. Total packets: %d.", node_id, packets)
            node_registry.remove(node_id)
            asyncio.create_task(ws_manager.broadcast({
                "type": "node_remove",
                "node_id": node_id
            }))
            return telemetry_pb2.TelemetryResponse(success=True, message="Stream closed")

        except asyncio.CancelledError:
            logger.info("Stream from [%s] cancelled (server shutting down).", node_id)
            node_registry.remove(node_id)
            asyncio.create_task(ws_manager.broadcast({
                "type": "node_remove",
                "node_id": node_id
            }))
            return telemetry_pb2.TelemetryResponse(success=False, message="Server shutting down")

        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error from [%s]: %s", node_id, exc)
            node_registry.remove(node_id)
            asyncio.create_task(ws_manager.broadcast({
                "type": "node_remove",
                "node_id": node_id
            }))
            return telemetry_pb2.TelemetryResponse(success=False, message=str(exc))


async def serve_grpc(observer) -> None:
    """
    Start the async gRPC server with a live ``observer`` instance.
    Blocks until cancelled; handles graceful shutdown with a 5-second grace period.
    """
    server = grpc.aio.server()
    telemetry_pb2_grpc.add_TelemetryServiceServicer_to_server(
        TelemetryServicer(observer), server
    )
    server.add_insecure_port(GRPC_LISTEN_ADDR)
    await server.start()
    logger.info("gRPC server listening on %s", GRPC_LISTEN_ADDR)

    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        logger.info("Shutting down gRPC server…")
        await server.stop(grace=5)
        logger.info("gRPC server stopped.")


