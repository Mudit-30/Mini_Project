"""
gridmind_server.app.grpc_server
---------------------------------
Receives client-streaming TelemetryData messages from Node Agents.

For every received packet the servicer:
  1. Builds a feature snapshot for Observer AI.
  2. Calls the Observer AI (with temporal smoothing) to classify state.
  3. Updates the in-memory NodeRegistry (fast REST/WS lookups).
  4. Broadcasts to WebSocket clients (fire-and-forget task).
  5. Persists a TelemetryRecord to SQLite (fire-and-forget task).

Peer extraction
---------------
gRPC context.peer() returns strings like:
  "ipv4:192.168.1.10:54321"
  "ipv6:[::1]:54321"
We extract only the host portion for use as the task-dispatch address.
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
from app.carbon.ledger import get_current_carbon

logger = logging.getLogger("gridmind.grpc")

GRPC_LISTEN_ADDR = "0.0.0.0:50051"


def _extract_host(peer: str) -> str:
    """
    Parse a gRPC peer string and return the bare IP host.

    Examples
    --------
    >>> _extract_host("ipv4:192.168.1.10:54321")
    '192.168.1.10'
    >>> _extract_host("ipv6:[::1]:54321")
    '::1'
    """
    if peer.startswith("ipv6:"):
        # strip prefix and port: "ipv6:[::1]:54321" → "::1"
        inner = peer[len("ipv6:"):]          # "[::1]:54321"
        if inner.startswith("["):
            host = inner[1:].split("]:")[0]  # "::1"
        else:
            host = inner.rsplit(":", 1)[0]
    elif peer.startswith("ipv4:"):
        inner = peer[len("ipv4:"):]          # "192.168.1.10:54321"
        host  = inner.rsplit(":", 1)[0]
    else:
        # Fallback: last colon-split
        host = peer.rsplit(":", 1)[0]
    return host or "127.0.0.1"


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
        self._db_buffer = []
        self._db_lock = asyncio.Lock()
        self._batch_size = 20
        self._bg_tasks = set()
        # Start a periodic flusher
        self._create_bg_task(self._flush_loop(), name="db-flusher")

    def _create_bg_task(self, coro, name: str) -> None:
        """Create a background task and keep a strong reference to prevent GC."""
        task = asyncio.create_task(coro, name=name)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(5)
            await self._flush_buffer()

    async def _flush_buffer(self) -> None:
        async with self._db_lock:
            if not self._db_buffer:
                return
            batch = self._db_buffer[:]
            self._db_buffer.clear()

        try:
            async with AsyncSessionLocal() as session:
                session.add_all(batch)
                await session.commit()
        except Exception as exc:
            logger.error("DB batch persist failed: %s", exc)

    # ── DB persistence (fire-and-forget) ──────────────────────────────────────
    async def _persist(self, record: TelemetryRecord) -> None:
        """Buffer a TelemetryRecord and flush if batch size is reached."""
        async with self._db_lock:
            self._db_buffer.append(record)
            should_flush = len(self._db_buffer) >= self._batch_size
        if should_flush:
            self._create_bg_task(self._flush_buffer(), name="db-flush-early")

    # ── gRPC streaming handler ─────────────────────────────────────────────────
    async def StreamTelemetry(
        self,
        request_iterator: grpc.aio.ServicerContext,
        context: grpc.aio.ServicerContext,
    ) -> telemetry_pb2.TelemetryResponse:
        node_id = "unknown"
        packets  = 0

        # Extract node host from gRPC peer *once* at stream open
        peer    = context.peer()
        address = _extract_host(peer)
        logger.debug("New telemetry stream from peer=%s → host=%s", peer, address)

        try:
            async for data in request_iterator:
                node_id  = data.node_id
                packets += 1

                # Real grid intensity (g/kWh) published by the dispatcher loop, so
                # both inference and the persisted row reflect the actual grid — not
                # a hardcoded 0.0 (which caused train/serve skew on retrain).
                carbon_now = get_current_carbon()

                # ── 1. Feature snapshot ──────────────────────────────────────
                snapshot = {
                    "cpu_usage_pct":         data.cpu_usage_pct,
                    "ram_usage_pct":         data.ram_usage_pct,
                    "kb_events_per_min":     data.kb_events_per_min,
                    "mouse_events_per_min":  data.mouse_events_per_min,
                    "net_io_bytes":          float(data.net_io_bytes),
                    "process_count":         data.process_count,
                    "cpu_cores":             data.cpu_cores,
                    "gpu_vram_gb":           data.gpu_vram_gb,
                    "has_docker":            data.has_docker,
                    "carbon_intensity_gco2": carbon_now,
                    "battery_percent":       data.battery_percent,
                    "on_battery":            data.on_battery,
                    "cpu_temp_c":            data.cpu_temp_c,
                }

                # ── 2. Observer AI prediction (with temporal smoothing) ──────
                try:
                    prediction = self._observer.predict(snapshot, node_id)
                except Exception as exc:
                    logger.warning("Observer.predict failed [%s]: %s", node_id, exc)
                    prediction = {"label": -1, "state": "unknown", "confidence": 0.0}

                # ── 3. Update in-memory registry ─────────────────────────────
                node_registry.update(node_id, snapshot, prediction, address=address)

                # ── 4. Broadcast to dashboard (fire-and-forget) ───────────────
                self._create_bg_task(
                    ws_manager.broadcast({
                        "type": "node_update",
                        "node": node_registry.get(node_id),
                    }),
                    name=f"ws-broadcast-{node_id}",
                )

                logger.debug(
                    "[%s] state=%-14s conf=%.2f  CPU=%5.1f%%  RAM=%5.1f%%",
                    node_id,
                    prediction["state"],
                    prediction["confidence"],
                    data.cpu_usage_pct,
                    data.ram_usage_pct,
                )

                # ── 5. Persist to SQLite (fire-and-forget) ────────────────────
                record = TelemetryRecord(
                    recorded_at           = datetime.datetime.now(datetime.timezone.utc),
                    node_id               = node_id,
                    cpu_usage_pct         = data.cpu_usage_pct,
                    ram_usage_pct         = data.ram_usage_pct,
                    kb_events_per_min     = data.kb_events_per_min,
                    mouse_events_per_min  = data.mouse_events_per_min,
                    net_io_bytes          = data.net_io_bytes,
                    process_count         = data.process_count,
                    carbon_intensity_gco2 = carbon_now,
                    predicted_label       = prediction["label"],
                    predicted_state       = prediction["state"],
                    prediction_confidence = prediction["confidence"],
                )
                await self._persist(record)

            # ── Clean disconnect ───────────────────────────────────────────────
            logger.info("Node [%s] disconnected cleanly. Packets received: %d.", node_id, packets)
            self._remove_node(node_id)
            return telemetry_pb2.TelemetryResponse(success=True, message="Stream closed cleanly.")

        except asyncio.CancelledError:
            logger.info("Stream from [%s] cancelled (server shutdown).", node_id)
            self._remove_node(node_id)
            return telemetry_pb2.TelemetryResponse(success=False, message="Server shutting down.")

        except Exception as exc:
            logger.error("Unexpected error in stream from [%s]: %s", node_id, exc, exc_info=True)
            self._remove_node(node_id)
            return telemetry_pb2.TelemetryResponse(success=False, message=str(exc))

    def _remove_node(self, node_id: str) -> None:
        """Remove node from registry, re-queue its in-flight tasks, and notify dashboard."""
        node_registry.remove(node_id)
        # Fault tolerance: a disconnected node may have had a task mid-flight —
        # re-queue it so another node finishes the work (requeue also broadcasts
        # the node_remove so the card disappears).
        from app.task_dispatcher import requeue_node_tasks
        self._create_bg_task(requeue_node_tasks(node_id), name=f"requeue-{node_id}")


async def serve_grpc(observer) -> None:
    """
    Start the async gRPC server, injecting *observer* into the servicer.
    Blocks until cancelled; shuts down with a 5-second grace period.

    Robustness: if the port is already bound (e.g. previous process still
    releasing it), we wait up to 10 seconds and retry once before failing.
    """
    import socket as _socket

    # One servicer instance, reused across bind retries (so we don't spawn duplicate
    # flush loops) and retained so we can flush its buffer on shutdown.
    servicer = TelemetryServicer(observer)

    async def _try_bind(retries: int = 3, delay: float = 3.0) -> grpc.aio.Server:
        for attempt in range(1, retries + 1):
            try:
                # Quick pre-check: is port already in use?
                s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
                s.settimeout(0.5)
                result = s.connect_ex(("127.0.0.1", 50051))
                s.close()
                if result == 0:
                    logger.warning(
                        "gRPC port 50051 still occupied (attempt %d/%d), waiting %.0fs…",
                        attempt, retries, delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                srv = grpc.aio.server()
                telemetry_pb2_grpc.add_TelemetryServiceServicer_to_server(servicer, srv)
                srv.add_insecure_port(GRPC_LISTEN_ADDR)
                await srv.start()
                return srv
            except RuntimeError as exc:
                logger.warning("gRPC bind failed (attempt %d/%d): %s", attempt, retries, exc)
                await asyncio.sleep(delay)
        raise RuntimeError(f"gRPC server could not bind to {GRPC_LISTEN_ADDR} after {retries} attempts.")

    server = await _try_bind()
    logger.info("gRPC server listening on %s", GRPC_LISTEN_ADDR)

    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        logger.info("Shutting down gRPC server (5s grace)…")
        # Persist any telemetry still sitting in the batch buffer before we go.
        try:
            await servicer._flush_buffer()
        except Exception as exc:
            logger.warning("Final telemetry flush failed: %s", exc)
        await server.stop(grace=5)
        logger.info("gRPC server stopped.")
    except Exception as exc:
        logger.error("gRPC server unexpected error: %s", exc, exc_info=True)
        await server.stop(grace=1)
