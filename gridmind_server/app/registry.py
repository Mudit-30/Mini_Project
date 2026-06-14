"""
gridmind_server.app.registry
==============================
Shared in-memory registry of the latest state for each connected node.

The gRPC servicer writes to this registry on every telemetry packet.
The REST API and Dispatcher loop read from it for low-latency queries.

Thread-safety
-------------
All mutations are protected by a threading.RLock so that both asyncio
coroutines (via the gRPC servicer) and APScheduler threads can access
it safely without deadlocking.
"""
from __future__ import annotations

import datetime
import threading
from typing import Any


class NodeRegistry:
    """
    Thread-safe dict of node_id → latest telemetry + Observer AI state.

    Each entry contains:
        node_id, last_seen, state, label, confidence,
        cpu_usage_pct, ram_usage_pct, kb_events_per_min,
        mouse_events_per_min, net_io_bytes, process_count,
        cpu_cores, gpu_vram_gb, has_docker,
        address (optional — filled from gRPC peer)
    """

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()   # Re-entrant: safe if the same thread calls multiple methods

    def update(
        self,
        node_id: str,
        telemetry: dict[str, Any],
        prediction: dict[str, Any],
        address: str | None = None,
    ) -> None:
        """Upsert the latest snapshot for a node."""
        # Preserve existing address if not supplied this tick
        with self._lock:
            existing = self._data.get(node_id, {})
            entry: dict[str, Any] = {
                "node_id":              node_id,
                "last_seen":            datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "state":                prediction["state"],
                "label":                prediction["label"],
                "confidence":           round(prediction["confidence"], 4),
                "cpu_usage_pct":        telemetry["cpu_usage_pct"],
                "ram_usage_pct":        telemetry["ram_usage_pct"],
                "kb_events_per_min":    telemetry["kb_events_per_min"],
                "mouse_events_per_min": telemetry["mouse_events_per_min"],
                "net_io_bytes":         telemetry["net_io_bytes"],
                "process_count":        telemetry["process_count"],
                "capabilities":         {
                    "cpu_cores":   telemetry.get("cpu_cores", 1),
                    "gpu_vram_gb": telemetry.get("gpu_vram_gb", 0.0),
                    "has_docker":  telemetry.get("has_docker", False),
                },
                "reliability_score":    existing.get("reliability_score", 1.0),
                "address":              address or existing.get("address", "127.0.0.1"),
                # Power / thermal state — drives the dispatcher's "don't drain a
                # teammate's battery / don't cook a hot laptop" protection.
                "battery_percent":      telemetry.get("battery_percent", 100.0),
                "on_battery":           telemetry.get("on_battery", False),
                "cpu_temp_c":           telemetry.get("cpu_temp_c", 0.0),
            }
            self._data[node_id] = entry

    def get(self, node_id: str) -> dict[str, Any] | None:
        with self._lock:
            node = self._data.get(node_id)
            return dict(node) if node else None

    def update_reliability(self, node_id: str, success: bool) -> None:
        with self._lock:
            if node_id in self._data:
                current_score = self._data[node_id].get("reliability_score", 1.0)
                if success:
                    new_score = min(1.0, current_score + 0.05)
                else:
                    new_score = max(0.0, current_score - 0.15)
                self._data[node_id]["reliability_score"] = new_score

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(v) for v in self._data.values()]

    def remove(self, node_id: str) -> None:
        with self._lock:
            self._data.pop(node_id, None)

    def safe_nodes(self) -> list[str]:
        """Return node_ids whose latest Observer AI state is 'idle'."""
        with self._lock:
            return [nid for nid, v in self._data.items() if v["state"] == "idle"]

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def __contains__(self, node_id: str) -> bool:
        with self._lock:
            return node_id in self._data


# Module-level singleton — imported by grpc_server, routes, and dispatcher_loop
node_registry = NodeRegistry()
