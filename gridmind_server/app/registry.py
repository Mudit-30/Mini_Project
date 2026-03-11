"""
gridmind_server.app.registry
==============================
Shared in-memory registry of the latest state for each connected node.

The gRPC servicer writes to this registry on every telemetry packet.
The REST API reads from it for low-latency node status queries.

Thread-safety: all mutations are protected by a `threading.Lock` so both
asyncio coroutines and background APScheduler threads can access it safely.
"""
from __future__ import annotations

import datetime
import threading
from typing import Any


class NodeRegistry:
    """
    Thread-safe dict of node_id → latest telemetry + Observer AI state.

    Each entry is a dict with:
        node_id, last_seen, state, confidence, label,
        cpu_usage_pct, ram_usage_pct, kb_events_per_min,
        mouse_events_per_min, net_io_bytes, process_count
    """

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def update(self, node_id: str, telemetry: dict[str, Any], prediction: dict[str, Any]) -> None:
        """Upsert the latest snapshot for a node."""
        entry = {
            "node_id":            node_id,
            "last_seen":          datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "state":              prediction["state"],
            "label":              prediction["label"],
            "confidence":         prediction["confidence"],
            "cpu_usage_pct":      telemetry["cpu_usage_pct"],
            "ram_usage_pct":      telemetry["ram_usage_pct"],
            "kb_events_per_min":  telemetry["kb_events_per_min"],
            "mouse_events_per_min": telemetry["mouse_events_per_min"],
            "net_io_bytes":       telemetry["net_io_bytes"],
            "process_count":      telemetry["process_count"],
        }
        with self._lock:
            self._data[node_id] = entry

    def get(self, node_id: str) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._data[node_id]) if node_id in self._data else None

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(v) for v in self._data.values()]

    def remove(self, node_id: str) -> None:
        with self._lock:
            self._data.pop(node_id, None)

    def safe_nodes(self) -> list[str]:
        """Return node_ids whose latest state is 'idle' (safe to dispatch tasks to)."""
        with self._lock:
            return [nid for nid, v in self._data.items() if v["state"] == "idle"]

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


# Singleton — imported by grpc_server, routes, and the retrain job
node_registry = NodeRegistry()
