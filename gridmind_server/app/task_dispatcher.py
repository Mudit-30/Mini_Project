"""
gridmind_server.app.task_dispatcher
-------------------------------------
Dispatches a task to a specific node via gRPC and streams execution
results back to the WebSocket dashboard.

Responsibilities
----------------
1. Mark the task as "running" in SQLite.
2. Open a gRPC channel to the node's task-server (port 50052).
3. Send the TaskPayload and stream TaskResult messages back.
4. Broadcast each stdout line to WebSocket clients in real-time.
5. On stream completion, persist final status / exit_code / stderr to DB.
6. On error, mark the task as "failed" and broadcast the error.

Stdout accumulation
-------------------
The executor streams stdout *line by line*. We accumulate all lines in a
list and join them into the final ``stdout`` field for DB persistence.
"""
from __future__ import annotations

import asyncio
import datetime
import logging

import grpc
import grpc.aio
from app.db.database import AsyncSessionLocal, TaskRecord, select, update
from app import telemetry_pb2, telemetry_pb2_grpc
from app.registry import node_registry
from app.websockets import manager as ws_manager
from app.carbon.ledger import carbon_ledger, get_current_carbon

logger = logging.getLogger("gridmind.task_dispatcher")

NODE_TASK_PORT = 50052
DEFAULT_TIMEOUT_S = 300
MAX_TASK_RETRIES = 3   # re-queue an in-flight task this many times after node failure


async def requeue_node_tasks(node_id: str) -> None:
    """
    A node disconnected — re-queue any task it was running so another node can
    pick it up (fault tolerance). Tasks past the retry cap are marked failed.
    Guarded by `status IN ('dispatched','running')` so it's idempotent with the
    dispatch-failure path (whichever fires first wins; the other no-ops).
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        async with AsyncSessionLocal() as session:
            # Under the cap → back to the pending queue for re-dispatch elsewhere.
            await session.execute(
                "UPDATE tasks SET status='pending', assigned_node=NULL, dispatched_at=NULL, "
                "retry_count=retry_count+1 "
                "WHERE assigned_node=? AND status IN ('dispatched','running') AND retry_count < ?",
                (node_id, MAX_TASK_RETRIES),
            )
            # Out of retries → give up honestly.
            await session.execute(
                "UPDATE tasks SET status='failed', completed_at=?, "
                "stderr='Node disconnected and retry limit reached.' "
                "WHERE assigned_node=? AND status IN ('dispatched','running') AND retry_count >= ?",
                (now, node_id, MAX_TASK_RETRIES),
            )
        logger.info("Re-queued in-flight tasks for disconnected node '%s'.", node_id)
        await ws_manager.broadcast({"type": "node_remove", "node_id": node_id})
    except Exception as exc:
        logger.error("requeue_node_tasks failed for %s: %s", node_id, exc)


async def _update_task_db(task_id: str, **fields) -> None:
    """Generic helper: update arbitrary fields on a TaskRecord row."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(TaskRecord).where(TaskRecord.task_id == task_id).values(**fields)
            )
            await session.commit()
    except Exception as exc:
        logger.error("DB update failed for task %s: %s", task_id, exc)


# Global registry of active dispatch tasks
_active_tasks: dict[str, asyncio.Task] = {}


async def cancel_active_task(task_id: str) -> bool:
    """Cancel a running dispatch task. Returns True if cancelled."""
    task = _active_tasks.get(task_id)
    if task:
        task.cancel()
        return True
    return False


async def dispatch_task_to_node(node_address: str, task_dict: dict) -> None:
    """
    Open gRPC channel to *node_address*:50052, send the script, stream
    results to the WebSocket dashboard, and persist the final state to DB.

    Parameters
    ----------
    node_address :
        Bare IP or hostname of the target node (without port).
    task_dict :
        Dict representation of a TaskRecord (from ``TaskRecord.to_dict()``).
    """
    task_id  = task_dict["task_id"]
    script   = task_dict["script"]
    priority = task_dict.get("priority_str", "deferrable")
    target   = f"{node_address}:{NODE_TASK_PORT}"

    # Check if already cancelled
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TaskRecord).where(TaskRecord.task_id == task_id)
        )
        t_rec = result.scalar_one_or_none()
        if t_rec and t_rec.status == "cancelled":
            logger.info("Task %s was cancelled before dispatch started.", task_id)
            return

    logger.info("Dispatching task %s → %s (priority=%s)", task_id, target, priority)

    # Register task for cancellation support
    _active_tasks[task_id] = asyncio.current_task()

    # Mark as running immediately
    await _update_task_db(task_id, status="running")

    # Capture the grid intensity at the moment GridMind RUNS the task. The shared
    # current-carbon value is advanced every ~2s by the dispatcher loop, so reading
    # it at completion (for a multi-second task) would record the wrong intensity
    # and corrupt the carbon-savings figure. Stamp it once, here, at dispatch start.
    run_carbon_gco2 = get_current_carbon()

    stdout_lines: list[str] = []

    # Try the registered address first. Only fall back to loopback for a LOCAL
    # node (its peer came through as ::1 / localhost). For a genuinely REMOTE node
    # we must NOT fall back to 127.0.0.1 — that would silently run the task on the
    # master (masking a closed firewall on the node) instead of failing honestly
    # and re-queuing. A real remote dispatch must reach the node directly.
    addresses_to_try = [node_address]
    _is_loopback = node_address in ("127.0.0.1", "localhost", "::1") or node_address.startswith("127.")
    if _is_loopback and node_address != "127.0.0.1":
        addresses_to_try.append("127.0.0.1")

    last_exc = None
    success = False

    try:
        for addr in addresses_to_try:
            current_target = f"{addr}:{NODE_TASK_PORT}"
            logger.info("Attempting dispatch task %s → %s", task_id, current_target)
            try:
                async with grpc.aio.insecure_channel(current_target) as channel:
                    stub    = telemetry_pb2_grpc.TelemetryServiceStub(channel)
                    payload = telemetry_pb2.TaskPayload(
                        task_id  = task_id,
                        script   = script,
                        timeout_s= DEFAULT_TIMEOUT_S,
                        priority = priority,
                        has_artifact = bool(task_dict.get("has_artifact", False)),
                        chunk_index = int(task_dict.get("chunk_index", 0) or 0),
                        chunk_count = int(task_dict.get("chunk_count", 1) or 1),
                    )

                    async for result in stub.RunTask(payload):
                        success = True
                        # Accumulate stdout for final DB write
                        if result.stdout:
                            stdout_lines.append(result.stdout)

                        # Broadcast live to dashboard
                        await ws_manager.broadcast({
                            "type":         "task_output",
                            "task_id":      task_id,
                            "stdout":       result.stdout,
                            "stderr":       result.stderr,
                            "status":       result.status,
                            "exit_code":    result.exit_code,
                            "duration_secs": result.duration_secs,
                        })

                        # When execution finishes, persist final state
                        if result.status in ("completed", "failed", "aborted"):
                            await _update_task_db(
                                task_id,
                                status       = result.status,
                                exit_code    = result.exit_code,
                                stdout       = "".join(stdout_lines),
                                stderr       = result.stderr,
                                duration_secs= result.duration_secs,
                                completed_at = datetime.datetime.now(datetime.timezone.utc),
                            )
                            logger.info(
                                "Task %s finished: status=%s exit=%s duration=%.1fs",
                                task_id, result.status, result.exit_code, result.duration_secs,
                            )

                            # ── Carbon ledger: record the real baseline-vs-GridMind
                            # emissions for this task (only count work that succeeded).
                            if result.status == "completed" and result.exit_code == 0:
                                carbon_ledger.record_task(
                                    duration_secs=result.duration_secs,
                                    submit_gco2=task_dict.get("submit_carbon_gco2"),
                                    run_gco2=run_carbon_gco2,
                                )

                            # Update Node Reliability Score
                            node_id = task_dict.get("assigned_node")
                            if node_id:
                                is_success = (result.status == "completed" and result.exit_code == 0)
                                node_registry.update_reliability(node_id, is_success)

                if success:
                    # Flush post-terminal stdout (e.g. artifact packaging/upload lines
                    # the executor emits after the completed/failed result) so the
                    # persisted log matches what the dashboard streamed live.
                    await _update_task_db(task_id, stdout="".join(stdout_lines))
                    break
            except grpc.RpcError as exc:
                if exc.code() == grpc.StatusCode.UNAVAILABLE:
                    logger.warning("Target %s unavailable, trying next target address...", current_target)
                    last_exc = exc
                    continue
                else:
                    raise
        else:
            if last_exc:
                raise last_exc
            else:
                raise Exception("No connection attempts succeeded.")

    except asyncio.CancelledError:
        logger.info("Task %s cancelled during active execution — aborting on node.", task_id)
        # Local task.cancel() only stops us streaming; the node's child subprocess
        # keeps running unless we explicitly tell it to abort. Send AbortTask.
        for addr in addresses_to_try:
            try:
                async with grpc.aio.insecure_channel(f"{addr}:{NODE_TASK_PORT}") as ch:
                    stub = telemetry_pb2_grpc.TelemetryServiceStub(ch)
                    ack = await asyncio.wait_for(
                        stub.AbortTask(telemetry_pb2.AbortRequest(task_id=task_id)), timeout=5
                    )
                    if ack.success:
                        break
            except Exception as exc:
                logger.debug("AbortTask to %s failed: %s", addr, exc)
        await _update_task_db(
            task_id,
            status       = "cancelled",
            stderr       = "Cancelled by user request.",
            completed_at = datetime.datetime.now(datetime.timezone.utc),
        )
        await ws_manager.broadcast({
            "type":    "task_output",
            "task_id": task_id,
            "status":  "cancelled",
            "stderr":  "Cancelled by user request.",
        })
        raise

    except Exception as exc:
        logger.error("Error dispatching task %s to %s: %s", task_id, target, exc, exc_info=True)
        retries = int(task_dict.get("retry_count", 0) or 0)
        node_id = task_dict.get("assigned_node")
        if node_id:
            node_registry.update_reliability(node_id, False)

        if retries + 1 <= MAX_TASK_RETRIES:
            # Node unreachable → re-queue for another node (fault tolerance).
            # Guarded UPDATE so it no-ops if requeue_node_tasks already handled it.
            logger.warning(
                "Dispatch of %s failed (%s) — re-queueing (attempt %d/%d).",
                task_id, exc, retries + 1, MAX_TASK_RETRIES,
            )
            try:
                async with AsyncSessionLocal() as session:
                    await session.execute(
                        "UPDATE tasks SET status='pending', assigned_node=NULL, dispatched_at=NULL, "
                        "retry_count=? WHERE task_id=? AND status IN ('dispatched','running')",
                        (retries + 1, task_id),
                    )
            except Exception as e2:
                logger.error("Re-queue update failed for %s: %s", task_id, e2)
            await ws_manager.broadcast({
                "type": "task_output", "task_id": task_id, "status": "pending",
                "stderr": f"Node unreachable — automatically re-queued (attempt {retries + 1}/{MAX_TASK_RETRIES}).",
            })
        else:
            err_msg = f"Dispatch failed after {MAX_TASK_RETRIES} retries: {exc}"
            await _update_task_db(
                task_id, status="failed", exit_code=1,
                stdout="".join(stdout_lines), stderr=err_msg,
                completed_at=datetime.datetime.now(datetime.timezone.utc),
            )
            await ws_manager.broadcast({
                "type": "task_output", "task_id": task_id, "status": "failed",
                "exit_code": 1, "stderr": err_msg,
            })

    finally:
        _active_tasks.pop(task_id, None)
