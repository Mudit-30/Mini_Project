"""
GridMind Node Agent
=====================
Collects hardware telemetry (CPU, RAM, keyboard/mouse events, net I/O)
and streams it to the central GridMind server via gRPC.

Run:
    python agent.py
    python agent.py --server 192.168.1.100:50051
"""
import argparse
import logging
import signal
import socket
import sys
import time
import threading

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, IOError):
        pass

import grpc
import psutil
import telemetry_pb2
import telemetry_pb2_grpc
from pynput import keyboard, mouse

# ── Configuration ──────────────────────────────────────────────────────────────
DEFAULT_SERVER   = "localhost:50051"
COLLECT_INTERVAL = 5          # seconds between telemetry samples
MAX_BACKOFF      = 60         # max reconnect delay in seconds
LOG_LEVEL        = logging.INFO

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gridmind.agent")


# ── Telemetry Collector ─────────────────────────────────────────────────────────
class TelemetryCollector:
    """
    Collects hardware telemetry via psutil and tracks human-input events
    (keyboard / mouse) using non-blocking pynput background listeners.
    Thread-safe: event counters are protected by a Lock.
    """

    def __init__(self):
        # Warm up the cpu_percent call so first reading is not always 0.0
        psutil.cpu_percent(interval=None)
        self._net_io_baseline = psutil.net_io_counters()

        self._kb_events    = 0
        self._mouse_events = 0
        self._lock         = threading.Lock()
        self._last_collect = time.monotonic()

        # pynput listeners run in their own daemon threads
        self._kb_listener = keyboard.Listener(
            on_press=self._count_kb,
            on_release=self._count_kb,
            daemon=True,
        )
        self._mouse_listener = mouse.Listener(
            on_move=self._count_mouse,
            on_click=self._count_mouse,
            on_scroll=self._count_mouse,
            daemon=True,
        )
        self._kb_listener.start()
        self._mouse_listener.start()
        logger.debug("Input listeners started.")

    # ── Event callbacks (called from pynput threads) ──────────────────────────
    def _count_kb(self, *_):
        with self._lock:
            self._kb_events += 1

    def _count_mouse(self, *_):
        with self._lock:
            self._mouse_events += 1

    # ── Main collection method ─────────────────────────────────────────────────
    def collect(self) -> dict:
        """
        Snapshot current hardware state and return a telemetry dict.
        Event counts are reset after each call so values represent
        activity *since the last collection*, normalised to per-minute rates.
        """
        now     = time.monotonic()
        elapsed = max(now - self._last_collect, 1e-3)   # guard against div/0
        self._last_collect = now

        # Atomically drain event counters
        with self._lock:
            kb_count    = self._kb_events;    self._kb_events    = 0
            mouse_count = self._mouse_events; self._mouse_events = 0

        # Hardware readings
        cpu_pct = psutil.cpu_percent(interval=None)
        ram_pct = psutil.virtual_memory().percent
        procs   = len(psutil.pids())

        # Network I/O delta
        net_now  = psutil.net_io_counters()
        net_delta = (
            (net_now.bytes_sent - self._net_io_baseline.bytes_sent) +
            (net_now.bytes_recv - self._net_io_baseline.bytes_recv)
        )
        self._net_io_baseline = net_now

        return {
            "cpu_usage_pct":        round(cpu_pct, 2),
            "ram_usage_pct":        round(ram_pct, 2),
            "kb_events_per_min":    int(kb_count    / elapsed * 60),
            "mouse_events_per_min": int(mouse_count / elapsed * 60),
            "net_io_bytes":         net_delta,
            "process_count":        procs,
        }

    def stop(self):
        """Cleanly stop the background input listeners."""
        self._kb_listener.stop()
        self._mouse_listener.stop()
        logger.debug("Input listeners stopped.")


# ── gRPC streaming ─────────────────────────────────────────────────────────────
def _telemetry_generator(collector: TelemetryCollector, node_id: str):
    """
    Generator that yields TelemetryData protobuf messages at a fixed interval.
    Controls its own pacing so the gRPC call stays open indefinitely.
    """
    while True:
        time.sleep(COLLECT_INTERVAL)
        data = collector.collect()
        logger.debug("Telemetry snapshot: %s", data)
        yield telemetry_pb2.TelemetryData(
            node_id             = node_id,
            cpu_usage_pct       = data["cpu_usage_pct"],
            ram_usage_pct       = data["ram_usage_pct"],
            kb_events_per_min   = data["kb_events_per_min"],
            mouse_events_per_min= data["mouse_events_per_min"],
            net_io_bytes        = data["net_io_bytes"],
            process_count       = data["process_count"],
        )


# ── Main loop with exponential-backoff reconnect ───────────────────────────────
def run(server_address: str, node_id_override: str | None = None):
    node_id   = node_id_override or socket.gethostname()
    collector = TelemetryCollector()
    backoff   = 2  # seconds

    # Graceful shutdown on SIGINT / SIGTERM
    _stop = threading.Event()
    def _handle_signal(sig, frame):
        logger.info("Shutdown signal received. Stopping agent…")
        _stop.set()
    signal.signal(signal.SIGINT,  _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info("Starting GridMind agent [node_id=%s, server=%s]", node_id, server_address)

    while not _stop.is_set():
        try:
            with grpc.insecure_channel(server_address) as channel:
                stub = telemetry_pb2_grpc.TelemetryServiceStub(channel)
                logger.info("Connected to GridMind server at %s", server_address)
                response = stub.StreamTelemetry(_telemetry_generator(collector, node_id))
                logger.info("Stream ended — server said: %s", response.message)
                backoff = 2  # reset backoff on clean disconnect

        except grpc.RpcError as exc:
            if _stop.is_set():
                break
            logger.warning(
                "gRPC error (%s): %s — reconnecting in %ds…",
                exc.code(), exc.details(), backoff,
            )
            _stop.wait(timeout=backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)

    collector.stop()
    logger.info("Agent stopped cleanly.")


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GridMind Node Agent")
    parser.add_argument(
        "--server",
        default=DEFAULT_SERVER,
        help=f"gRPC server address (default: {DEFAULT_SERVER})",
    )
    parser.add_argument(
        "--node-id",
        default=None,
        help="Custom node ID (default: hostname)",
    )
    args = parser.parse_args()
    
    run(args.server, args.node_id)
