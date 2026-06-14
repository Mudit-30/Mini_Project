"""
GridMind Node Agent
=====================
Collects hardware telemetry (CPU, RAM, keyboard/mouse events, net I/O)
and streams it to the central GridMind server via gRPC.

Dual-port architecture:
  - Port 50051: outbound client-streaming telemetry → server
  - Port 50052: inbound task server ← server (RunTask / AbortTask)

Run:
    python agent.py
    python agent.py --server 192.168.1.100:50051
    python agent.py --server 192.168.1.100:50051 --node-id my-laptop
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import socket
import sys
import threading
import time

# ── Windows UTF-8 console fix (for emoji logging) ─────────────────────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, IOError):
        pass

import grpc
import grpc.aio
import psutil
import telemetry_pb2
import telemetry_pb2_grpc
from executor import abort_task, run_script
import pynput
from pynput import keyboard, mouse
import shutil

try:
    import pynvml
    pynvml.nvmlInit()
    HAS_PYNVML = True
except Exception:
    HAS_PYNVML = False

# ── Configuration ─────────────────────────────────────────────────────────────
DEFAULT_SERVER    = "localhost:50051"
NODE_SERVER_PORT  = 50052
COLLECT_INTERVAL  = 5      # seconds between telemetry samples
MAX_BACKOFF       = 60     # max reconnect delay (seconds)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gridmind.agent")


# ── Telemetry Collector ────────────────────────────────────────────────────────
class TelemetryCollector:
    """
    Collects hardware telemetry via psutil and tracks human-input events
    (keyboard / mouse) using non-blocking pynput background listeners.

    Thread-safe: event counters are protected by a threading.Lock.
    Event counts are reset after each ``collect()`` call so values represent
    activity *since the last collection*, normalised to per-minute rates.
    """

    def __init__(self) -> None:
        psutil.cpu_percent(interval=None)          # warm-up: first call is always 0.0
        self._net_baseline = psutil.net_io_counters()
        self._kb_events    = 0
        self._mouse_events = 0
        self._lock         = threading.Lock()
        self._last_collect = time.monotonic()

        self._kb_listener = keyboard.Listener(
            on_press=self._on_kb, on_release=self._on_kb, daemon=True
        )
        self._mouse_listener = mouse.Listener(
            on_move=self._on_mouse_move,      # telemetry only — NOT a burst signal
            on_click=self._on_mouse_action,
            on_scroll=self._on_mouse_action,
            daemon=True,
        )
        self._kb_listener.start()
        self._mouse_listener.start()
        logger.debug("Input listeners started.")

    # ── Event callbacks (called from pynput threads) ──────────────────────────
    def _on_kb(self, *_) -> None:
        with self._lock:
            self._kb_events += 1
        _register_input_event()

    def _on_mouse_move(self, *_) -> None:
        # pynput fires on_move dozens of times/second on any cursor motion. Count it
        # for telemetry, but do NOT treat it as deliberate interaction — otherwise the
        # burst-abort would fire the instant the cursor twitches near the machine.
        with self._lock:
            self._mouse_events += 1

    def _on_mouse_action(self, *_) -> None:
        # Clicks and scrolls ARE deliberate interaction → count + feed burst detection.
        with self._lock:
            self._mouse_events += 1
        _register_input_event()

    # ── Main collection ───────────────────────────────────────────────────────
    def collect(self) -> dict:
        """Return a telemetry snapshot and reset per-interval counters."""
        now     = time.monotonic()
        elapsed = max(now - self._last_collect, 1e-3)
        self._last_collect = now

        with self._lock:
            kb_count    = self._kb_events;    self._kb_events    = 0
            mouse_count = self._mouse_events; self._mouse_events = 0

        cpu_pct  = psutil.cpu_percent(interval=None)
        ram_info = psutil.virtual_memory()
        procs    = len(psutil.pids())

        net_now   = psutil.net_io_counters()
        net_delta = (
            (net_now.bytes_sent - self._net_baseline.bytes_sent)
            + (net_now.bytes_recv - self._net_baseline.bytes_recv)
        )
        self._net_baseline = net_now

        has_docker = bool(shutil.which("docker"))
        cpu_cores = psutil.cpu_count(logical=True) or 1

        # Battery / power state — the whole point of running on personal laptops:
        # don't drain someone's battery. Desktops (no battery) report 100% / plugged.
        battery_percent = 100.0
        on_battery = False
        try:
            batt = psutil.sensors_battery()
            if batt is not None:
                battery_percent = float(batt.percent)
                on_battery = not batt.power_plugged
        except Exception:
            pass

        # CPU temperature — frequently unavailable on Windows (no attribute / empty);
        # 0.0 means "unknown" and the dispatcher simply skips the thermal guard.
        cpu_temp_c = 0.0
        try:
            temps_fn = getattr(psutil, "sensors_temperatures", None)
            if temps_fn:
                readings = [r.current for arr in temps_fn().values() for r in arr if r.current]
                if readings:
                    cpu_temp_c = float(max(readings))
        except Exception:
            pass
        
        # Actual GPU check using pynvml if available (sum total VRAM across all GPUs)
        gpu_vram = 0.0
        if HAS_PYNVML:
            try:
                count = pynvml.nvmlDeviceGetCount()
                total_bytes = 0
                for i in range(count):
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                    total_bytes += pynvml.nvmlDeviceGetMemoryInfo(handle).total
                gpu_vram = total_bytes / (1024 ** 3)  # bytes → GB
            except Exception as exc:
                logger.debug("GPU VRAM probe failed: %s", exc)   # distinguish from no-GPU

        return {
            "cpu_usage_pct":        round(cpu_pct, 2),
            "ram_usage_pct":        round(ram_info.percent, 2),
            "kb_events_per_min":    int(kb_count    / elapsed * 60),
            "mouse_events_per_min": int(mouse_count / elapsed * 60),
            "net_io_bytes":         max(0, net_delta),  # guard against counter resets
            "process_count":        procs,
            "cpu_cores":            cpu_cores,
            "gpu_vram_gb":          gpu_vram,
            "has_docker":           has_docker,
            "battery_percent":      round(battery_percent, 1),
            "on_battery":           on_battery,
            "cpu_temp_c":           round(cpu_temp_c, 1),
        }

    def stop(self) -> None:
        """Cleanly stop the background input listeners."""
        self._kb_listener.stop()
        self._mouse_listener.stop()
        logger.debug("Input listeners stopped.")


# ── Abort state ───────────────────────────────────────────────────────────────
_active_task_id: str | None = None
_active_task_lock = threading.Lock()

# Burst detection: track recent input events to avoid aborting on accidental single keystrokes
_input_event_times: list[float] = []
_input_event_lock = threading.Lock()
_BURST_THRESHOLD = 12      # deliberate events (keys/clicks/scrolls) needed to abort
_BURST_WINDOW_S  = 10.0    # within this many seconds
_main_loop: asyncio.AbstractEventLoop | None = None


def _register_input_event() -> None:
    """
    Record an input event timestamp. If enough events occur within the burst
    window, and a task is running, schedule an abort.
    Fast-path: do nothing if no task is running.
    """
    # Deliberate lock-free read: a global-name read is atomic under the GIL and
    # _trigger_abort_check re-reads under _active_task_lock, so the worst case is a
    # one-event boundary wobble — never a crash or torn value.
    if _active_task_id is None:
        return

    now = time.monotonic()
    with _input_event_lock:
        _input_event_times.append(now)
        # Prune old events outside the window
        cutoff = now - _BURST_WINDOW_S
        while _input_event_times and _input_event_times[0] < cutoff:
            _input_event_times.pop(0)
        burst_count = len(_input_event_times)

    if burst_count >= _BURST_THRESHOLD:
        _trigger_abort_check()


def _trigger_abort_check() -> None:
    """
    Schedules abort_task via asyncio if a task is actively running.
    """
    with _active_task_lock:
        task_id = _active_task_id
    if task_id is None:
        return
    try:
        if _main_loop and _main_loop.is_running():
            _main_loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(abort_task(task_id))
            )
    except Exception as exc:
        logger.debug("Failed to schedule abort_task: %s", exc)


# ── Node gRPC Servicer ────────────────────────────────────────────────────────
class NodeServicer(telemetry_pb2_grpc.TelemetryServiceServicer):
    """
    Handles task execution requests from the GridMind server.
    Exposed on port 50052.
    """
    def __init__(self, server_address: str):
        # Extract the host (IP/domain) from the gRPC address to build the HTTP REST URL
        self.server_host = server_address.split(":")[0]

    async def RunTask(self, request, context):
        global _active_task_id
        with _active_task_lock:
            _active_task_id = request.task_id

        # Highly visible notification in the worker node's terminal
        artifact_msg = "with ZIP Workspace" if request.has_artifact else "Script"
        if sys.platform == "win32":
            try:
                with open("CONOUT$", "w", encoding="utf-8") as con:
                    con.write(f"\n" + "="*60 + "\n")
                    con.write(f"[📥 GRIDMIND WORKER] RECEIVED TASK FROM MASTER!\n")
                    con.write(f" -> Task ID: {request.task_id[:8]}...\n")
                    con.write(f" -> Payload: {artifact_msg}\n")
                    con.write("="*60 + "\n\n")
            except Exception:
                print(f"\n[📥 GRIDMIND WORKER] RECEIVED TASK FROM MASTER! ({artifact_msg})\n")
        else:
            print(f"\n[📥 GRIDMIND WORKER] RECEIVED TASK FROM MASTER! ({artifact_msg})\n")

        start = time.monotonic()
        try:
            async for result in run_script(
                request.task_id,
                request.script,
                request.timeout_s or 300,
                has_artifact=request.has_artifact,
                server_host=self.server_host,
                chunk_index=request.chunk_index,
                chunk_count=request.chunk_count or 1,
            ):
                result["duration_secs"] = round(time.monotonic() - start, 2)
                yield telemetry_pb2.TaskResult(**result)
        except Exception as exc:
            logger.error("Unhandled exception in task execution: %s", exc)
            yield telemetry_pb2.TaskResult(
                task_id=request.task_id,
                stdout="",
                stderr=f"Agent internal error: {exc}",
                exit_code=-2,
                status="failed",
                duration_secs=round(time.monotonic() - start, 2)
            )
        finally:
            with _active_task_lock:
                _active_task_id = None

    async def AbortTask(self, request, context):
        success = await abort_task(request.task_id)
        return telemetry_pb2.AbortAck(success=success)


# ── Telemetry Generator ───────────────────────────────────────────────────────
async def _telemetry_generator(
    collector: TelemetryCollector,
    node_id: str,
    stop_event: asyncio.Event,
):
    """
    Async generator that yields TelemetryData protobuf messages at a fixed
    interval. Drives the outbound client-streaming gRPC call.
    """
    while not stop_event.is_set():
        await asyncio.sleep(COLLECT_INTERVAL)
        data = collector.collect()
        logger.debug("Telemetry: %s", data)
        yield telemetry_pb2.TelemetryData(
            node_id              = node_id,
            cpu_usage_pct        = data["cpu_usage_pct"],
            ram_usage_pct        = data["ram_usage_pct"],
            kb_events_per_min    = data["kb_events_per_min"],
            mouse_events_per_min = data["mouse_events_per_min"],
            net_io_bytes         = data["net_io_bytes"],
            process_count        = data["process_count"],
            cpu_cores            = data["cpu_cores"],
            gpu_vram_gb          = data["gpu_vram_gb"],
            has_docker           = data["has_docker"],
            battery_percent      = data["battery_percent"],
            on_battery           = data["on_battery"],
            cpu_temp_c           = data["cpu_temp_c"],
        )


# ── Main run loop (exponential-backoff reconnect) ─────────────────────────────
async def run(server_address: str, node_id_override: str | None = None,
              task_port: int = NODE_SERVER_PORT) -> None:
    global _main_loop
    node_id   = node_id_override or socket.gethostname()
    collector = TelemetryCollector()
    backoff   = 2

    stop_event = asyncio.Event()
    _main_loop = asyncio.get_running_loop()

    def _signal_handler(*_):
        logger.info("Shutdown signal — stopping agent…")
        stop_event.set()

    if sys.platform != "win32":
        _main_loop.add_signal_handler(signal.SIGINT,  _signal_handler)
        _main_loop.add_signal_handler(signal.SIGTERM, _signal_handler)

    logger.info("GridMind agent starting [node_id=%s server=%s]", node_id, server_address)

    # ── Start node task-receiver gRPC server on 50052 ─────────────────────────
    node_server = grpc.aio.server()
    telemetry_pb2_grpc.add_TelemetryServiceServicer_to_server(NodeServicer(server_address), node_server)
    bound = node_server.add_insecure_port(f"0.0.0.0:{task_port}")
    if bound == 0:
        # add_insecure_port returns 0 on failure. Exit instead of streaming telemetry
        # as a "node" the server can never actually dispatch tasks to.
        logger.error(
            "Failed to bind node task server to 0.0.0.0:%d (port already in use?). Exiting.",
            task_port,
        )
        await node_server.stop(grace=0)
        sys.exit(1)
    await node_server.start()
    logger.info("Node task server listening on port %d", task_port)

    # ── Telemetry loop (outbound, with reconnect) ──────────────────────────────
    async def telemetry_loop() -> None:
        nonlocal backoff
        while not stop_event.is_set():
            try:
                async with grpc.aio.insecure_channel(server_address) as channel:
                    stub = telemetry_pb2_grpc.TelemetryServiceStub(channel)
                    logger.info("Connected to server at %s", server_address)
                    response = await stub.StreamTelemetry(
                        _telemetry_generator(collector, node_id, stop_event)
                    )
                    logger.info("Stream ended: %s", response.message)
                    backoff = 2  # reset on clean disconnect

            except grpc.RpcError as exc:
                if stop_event.is_set():
                    break
                logger.warning(
                    "gRPC error (%s): %s — reconnecting in %ds…",
                    exc.code(), exc.details(), backoff,
                )
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=backoff)
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2, MAX_BACKOFF)

            except Exception as exc:
                if stop_event.is_set():
                    break
                logger.error("Unexpected error in telemetry loop: %s", exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)

    tel_task = asyncio.create_task(telemetry_loop(), name="telemetry-loop")

    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        stop_event.set()

    # ── Graceful shutdown ──────────────────────────────────────────────────────
    stop_event.set()
    await node_server.stop(grace=3)
    collector.stop()
    tel_task.cancel()
    try:
        await tel_task
    except asyncio.CancelledError:
        pass
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
        help="Custom node ID (default: system hostname)",
    )
    parser.add_argument(
        "--task-port",
        type=int,
        default=int(os.environ.get("GRIDMIND_NODE_PORT", NODE_SERVER_PORT)),
        help=f"Inbound task-server port (default: {NODE_SERVER_PORT}). Use distinct "
             "ports when simulating multiple agents on one machine.",
    )
    args = parser.parse_args()

    try:
        asyncio.run(run(args.server, args.node_id, args.task_port))
    except KeyboardInterrupt:
        logger.info("Agent stopped by user.")
