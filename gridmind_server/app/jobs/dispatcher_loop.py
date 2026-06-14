"""
gridmind_server.app.jobs.dispatcher_loop
------------------------------------------
Background asyncio loop (2-second cadence) that drives the GridMind
Dispatcher AI decision cycle.

Each cycle:
  1. Count real pending tasks from SQLite (split by priority tier).
  2. Snapshot live node states from the in-memory registry.
  3. Look up real carbon intensity from the WattTime historical CSV.
  4. Build a 10-feature normalised state vector.
  5. Query the Dueling Double DQN for action: DEFER (0) or DISPATCH (1).
  6. If DISPATCH: pick the idle node with the lowest CPU and fire the task.
  7. Broadcast the full decision payload to WebSocket dashboard clients.

State vector layout (10 features, all in [0, 1]):
  [q_norm, carbon, idle_ratio, active_ratio, busy_ratio,
   avg_cpu, avg_ram, urgent_ratio, deferrable_ratio, best_effort_ratio]
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import math
from pathlib import Path

from app.db.database import AsyncSessionLocal, TaskRecord, func, select, update
from app.registry import node_registry
from app.task_dispatcher import dispatch_task_to_node
from app.websockets import manager as ws_manager
from app.carbon.forecaster import CarbonForecaster
from app.carbon.ledger import carbon_ledger, set_current_carbon

logger = logging.getLogger("gridmind.dispatcher")

# ── Carbon data ────────────────────────────────────────────────────────────────
import os
_CSV_PATH = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "watttime_carbon_data_CAISO_NORTH.csv")))

# The CSV is WattTime CO2_MOER — MARGINAL operating emissions (lbs CO2/MWh): the CO2
# of the next MWh, i.e. what actually changes when you shift load. We keep raw lbs and
# convert to g/kWh at broadcast time.
LBS_TO_GCO2 = 0.453592          # 1 lb/MWh == 0.453592 g/kWh
CLEAN_THRESHOLD_GCO2 = 450.0    # Below this = clean grid
DIRTY_THRESHOLD_GCO2 = 550.0    # Above this = dirty grid

CARBON_SERIES_LBS: list[float] = []     # raw lbs/MWh values
CARBON_MIN_LBS: float = 0.0
CARBON_MAX_LBS: float = 1.0

# Demo fast-forward: how many 5-minute CSV rows to advance per 2-second cycle.
# The CSV is 5-min resolution, so a full daily dirty→clean grid swing is ~288 rows.
#   stride=1  → ~9.6 min to traverse one day (near real-time, subtle)
#   stride=6  → ~96 s per daily swing (good for a live demo) ← default
# Override with env GRIDMIND_CARBON_STRIDE.
try:
    CARBON_STEP_STRIDE = max(1, int(os.environ.get("GRIDMIND_CARBON_STRIDE", "6")))
except ValueError:
    CARBON_STEP_STRIDE = 6

try:
    import csv as _csv
    with _CSV_PATH.open(mode="r", encoding="utf-8") as f:
        reader = _csv.DictReader(f)
        values = [float(row["value"]) for row in reader if row.get("value") and float(row["value"]) > 0]
    if values:
        CARBON_SERIES_LBS = values
        CARBON_MIN_LBS = min(values)
        CARBON_MAX_LBS = max(values)
        logger.info("Loaded %d real carbon data points (lbs/MWh) from CAISO NORTH. Range: %.1f–%.1f", len(values), CARBON_MIN_LBS, CARBON_MAX_LBS)
    else:
        raise ValueError("CSV has no value data")
except Exception as _exc:
    logger.warning("Carbon CSV parsing failed — using fallback: %s", _exc)

# Fit the ARIMA carbon model once at startup (statsmodels). Kept as the project's
# forecasting artifact; the live 2-hour outlook strip is driven by the replayed CSV
# series (computed per-cycle below), so this is not called in the hot loop.
carbon_forecaster = CarbonForecaster()
try:
    carbon_forecaster.fit()
    logger.info("CarbonForecaster initialized and fitted on historical data.")
except Exception as e:
    logger.error("Failed to fit CarbonForecaster: %s", e)

# Power/thermal protection thresholds for personal laptops.
MIN_BATTERY_PCT = 20.0    # below this, leave the laptop alone even if plugged
MAX_CPU_TEMP_C  = 85.0    # above this, don't add heat (only enforced if temp is known)


def _power_ok(node: dict) -> bool:
    """A node is safe to dispatch to only if we won't drain its battery or cook it."""
    if node.get("on_battery"):
        return False
    batt = node.get("battery_percent", 100.0)
    if batt and batt < MIN_BATTERY_PCT:
        return False
    temp = node.get("cpu_temp_c", 0.0)
    if temp and temp > MAX_CPU_TEMP_C:
        return False
    return True


# ── Helpers ───────────────────────────────────────────────────────────────────

def explain_decision(
    action: int,
    state: list[float],
    q_values: list[float],
    nodes: list,
    carbon_gco2: float = 0.0,
    clean_window: int | None = None,
) -> str:
    # clean_window is precomputed by the caller from the (dynamic) replayed grid
    # series — no per-cycle ARIMA .forecast() call in the hot loop.
    idle_frac    = state[2] * 100
    queue_depth  = int(state[0] * 20)
    queue_urgent = int(state[7] * 20)

    if action == 0:   # Defer
        parts = []
        if carbon_gco2 > CLEAN_THRESHOLD_GCO2:
            parts.append(f"grid is dirty ({carbon_gco2:.0f} g/kWh)")
            if clean_window is not None:
                parts.append(f"clean window in {clean_window} mins")
        if idle_frac == 0:
            parts.append("no idle nodes available")
        if queue_depth == 0:
            parts.append("queue is empty")
        return "Deferred: " + ("; ".join(parts) or "suboptimal conditions")
    else:
        best_node = next((n for n in nodes if n.get("state") == "idle"), None)
        max_q = max(q_values) if q_values else 0.0
        return (
            f"Dispatched to {best_node.get('node_id', 'unknown') if best_node else 'unknown'}: "
            f"grid at {carbon_gco2:.0f} g/kWh, "
            f"{idle_frac:.0f}% nodes idle, "
            f"Q-value={max_q:.3f}, "
            f"{queue_urgent} urgent tasks in queue"
        )

async def _get_priority_counts() -> tuple[int, int, int, int]:
    """
    Return (urgent, deferrable, best_effort, total) counts of pending tasks.
    Single DB query with GROUP BY for efficiency.
    """
    urgent = deferrable = best_effort = 0
    try:
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(TaskRecord.priority_str, func.count(TaskRecord.id))
                .where(TaskRecord.status == "pending")
                .group_by(TaskRecord.priority_str)
            )
            for priority, count in rows:
                if priority == "urgent":
                    urgent = count
                elif priority == "deferrable":
                    deferrable = count
                else:
                    best_effort = count
    except Exception as exc:
        logger.warning("Could not fetch priority counts: %s", exc)

    return urgent, deferrable, best_effort, urgent + deferrable + best_effort


# Strong references to in-flight dispatch tasks so the event loop can't GC-cancel
# them mid-execution (asyncio only holds weak refs to bare create_task() handles).
_inflight_dispatch: set[asyncio.Task] = set()


async def _dispatch_highest_priority_task(node_id: str, node_address: str) -> str | None:
    """
    Mark the highest-priority pending task as dispatched to *node_id* and
    trigger real gRPC execution on *node_address*.

    Priority order: urgent → deferrable → best_effort; FIFO within each tier.
    Ordering is now direction-aware in the ORM: priority_str DESC happens to be the
    correct tier order for these literals (urgent > deferrable > best_effort), and
    submitted_at ASC gives FIFO within a tier.
    Returns the dispatched task_id, or None if no pending task was found.
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(TaskRecord)
                .where(TaskRecord.status == "pending")
                .order_by(
                    TaskRecord.priority_str.desc(),
                    TaskRecord.submitted_at,
                )
                .limit(1)
            )
            task = result.scalar_one_or_none()
            if task is None:
                return None

            now = datetime.datetime.now(datetime.timezone.utc)
            # Mutate the loaded row only to build the gRPC payload (to_dict below);
            # the update() is what actually persists — commit() does NOT flush a
            # loaded-then-mutated row in this lightweight ORM.
            task.status        = "dispatched"
            task.assigned_node = node_id
            task.dispatched_at = now
            await db.execute(
                update(TaskRecord)
                .where(TaskRecord.task_id == task.task_id)
                .values(status="dispatched", assigned_node=node_id, dispatched_at=now)
            )
            await db.commit()

            logger.info(
                "Task '%s' (%s) dispatched → node '%s' @ %s",
                task.name, task.task_id, node_id, node_address,
            )
            task_dict = task.to_dict()

        # Execute asynchronously — fire-and-forget; result streamed via WebSocket.
        # Keep a strong reference until the task finishes.
        t = asyncio.create_task(
            dispatch_task_to_node(node_address, task_dict),
            name=f"exec-{task_dict['task_id'][:8]}",
        )
        _inflight_dispatch.add(t)
        t.add_done_callback(_inflight_dispatch.discard)
        return task_dict["task_id"]

    except Exception as exc:
        logger.error("Failed to dispatch task to %s: %s", node_id, exc, exc_info=True)
        return None


async def _nodes_with_inflight_tasks() -> set[str]:
    """Node IDs currently running a dispatched/running task — so we send at most
    one task per node (lets data-parallel chunks spread across the cluster)."""
    busy: set[str] = set()
    try:
        async with AsyncSessionLocal() as db:
            cur = await db.execute(
                "SELECT DISTINCT assigned_node FROM tasks "
                "WHERE status IN ('dispatched','running') AND assigned_node IS NOT NULL"
            )
            for row in await cur.fetchall():
                if row[0]:
                    busy.add(row[0])
    except Exception as exc:
        logger.warning("Could not fetch in-flight node set: %s", exc)
    return busy


# ── Main loop ─────────────────────────────────────────────────────────────────

async def run_dispatcher_loop(inference_engine) -> None:
    """
    Background loop: runs every 2 seconds, drives the Dispatcher AI
    decision-action cycle and pushes updates to the WebSocket dashboard.
    """
    logger.info("Dispatcher loop started. (carbon fast-forward stride=%d rows/cycle)", CARBON_STEP_STRIDE)
    # Wrap step counter to prevent unbounded growth (90-step sine period; CSV length safe)
    _STEP_WRAP = 360_000   # 10 hours at 2s cadence before wrapping
    step = 0

    while True:
        await asyncio.sleep(2)

        try:
            # ── 1. Priority counts (single aggregated query) ─────────────────
            urgent, deferrable, best_effort, total_pending = await _get_priority_counts()
            q_norm    = min(1.0, total_pending / 20.0)
            u_ratio   = urgent      / total_pending if total_pending else 0.0
            d_ratio   = deferrable  / total_pending if total_pending else 0.0
            b_ratio   = best_effort / total_pending if total_pending else 0.0

            # ── 2. Node stats from registry ───────────────────────────────────
            nodes       = node_registry.all()
            n_count     = len(nodes) or 1
            # Idle AND confidently so AND power/thermal-safe to use.
            idle_ready  = [n for n in nodes if n.get("state") == "idle" and n.get("confidence", 0.0) >= 0.50]
            idle_nodes  = [n for n in idle_ready if _power_ok(n)]
            # Idle nodes we deliberately skipped to protect battery/temperature.
            idle_protected = [n for n in idle_ready if not _power_ok(n)]
            active_nodes= [n for n in nodes if n.get("state") == "active_user"]
            busy_nodes  = [n for n in nodes if n.get("state") == "busy_hardware"]

            idle_ratio  = len(idle_nodes)   / n_count
            active_ratio= len(active_nodes) / n_count
            busy_ratio  = len(busy_nodes)   / n_count
            avg_cpu     = sum(n.get("cpu_usage_pct", 0) for n in nodes) / n_count / 100.0
            avg_ram     = sum(n.get("ram_usage_pct", 0) for n in nodes) / n_count / 100.0

            # ── 3. Carbon intensity (real lbs/MWh → g/kWh) ────────────────────
            if CARBON_SERIES_LBS:
                raw_lbs = CARBON_SERIES_LBS[step % len(CARBON_SERIES_LBS)]
            else:
                # Sine fallback in realistic lbs/MWh range (200–900)
                raw_lbs = 550 + 350 * math.sin(step * 2 * math.pi / 90)

            carbon_gco2 = round(raw_lbs * LBS_TO_GCO2, 1)   # real g/kWh (e.g. 120–450)
            # Publish for the task-submission route to stamp as the naive baseline.
            set_current_carbon(carbon_gco2)
            # Normalise to [0,1] for the DQN state vector
            carbon_norm = min(1.0, max(0.0,
                (raw_lbs - CARBON_MIN_LBS) / (CARBON_MAX_LBS - CARBON_MIN_LBS + 1e-9)
            ))

            # 2-hour grid outlook: the next 24 rows (5-min resolution) of the real
            # replayed CAISO series, in g/kWh. Dynamic — moves as the demo advances.
            if CARBON_SERIES_LBS:
                _n = len(CARBON_SERIES_LBS)
                carbon_forecast = [
                    round(CARBON_SERIES_LBS[(step + k) % _n] * LBS_TO_GCO2, 1)
                    for k in range(1, 25)
                ]
                clean_window_min = next(
                    (k * 5 for k, v in enumerate(carbon_forecast) if v < CLEAN_THRESHOLD_GCO2),
                    None,
                )
            else:
                carbon_forecast, clean_window_min = [], None

            # Advance step with wraparound (stride controls demo fast-forward speed)
            step = (step + CARBON_STEP_STRIDE) % _STEP_WRAP

            # ── 4. DQN inference ──────────────────────────────────────────────
            # Slot 9 MUST be best_effort_ratio (b_ratio): that is what the DuelingDQN
            # was trained on (see dispatcher_env.get_state). Feeding avg_reliability
            # here was a train/serve skew that corrupted the model's input.
            state_vector = [
                q_norm, carbon_norm,
                idle_ratio, active_ratio, busy_ratio,
                avg_cpu, avg_ram,
                u_ratio, d_ratio, b_ratio,
            ]
            try:
                action, q_values = inference_engine.predict_action(state_vector)
            except Exception as exc:
                logger.warning("DQN inference failed, defaulting to DEFER: %s", exc)
                action, q_values = 0, []

            # Force defer if there are no tasks, ignoring AI prediction
            if total_pending == 0:
                action = 0

            # Track which guardrail (if any) overrode the learned policy, for transparency.
            override: str | None = None

            # ── 5a. Urgent override: urgent work runs now, regardless of carbon ──
            # Real carbon-aware schedulers never hold urgent jobs for clean energy.
            if urgent > 0 and idle_nodes:
                action = 1
                override = "urgent"
            # ── 5b. Carbon-aware override: force dispatch if grid is green ──────
            elif total_pending > 0 and carbon_gco2 < CLEAN_THRESHOLD_GCO2 and idle_nodes:
                action = 1
                override = "clean-grid"

            # ── 6. Execute action ──────────────────────────────────────────────
            strategy_text: str
            dispatched_task_id: str | None = None
            if action == 0:
                if total_pending == 0:
                    strategy_text = "IDLE — Queue Empty"
                elif carbon_gco2 >= DIRTY_THRESHOLD_GCO2:
                    strategy_text = f"DEFERRING — Grid Dirty ({carbon_gco2:.0f} g/kWh)"
                elif not idle_nodes and idle_protected:
                    strategy_text = "DEFERRING — Protecting Node Battery/Temp 🔋"
                elif not idle_nodes:
                    strategy_text = "DEFERRING — All Nodes Busy"
                else:
                    strategy_text = "DEFERRING — AI Strategising"
            else:
                # Fan out: send one task to each FREE idle node (a node already
                # running a task is skipped), so the chunks of a data-parallel job
                # run concurrently across the cluster instead of one-per-2s-cycle.
                busy_with_task = await _nodes_with_inflight_tasks()
                free_nodes = sorted(
                    [n for n in idle_nodes if n["node_id"] not in busy_with_task],
                    key=lambda n: n.get("cpu_usage_pct", 100),
                )
                tag = " (urgent)" if override == "urgent" else ""
                dispatched_ids: list[str] = []
                for node in free_nodes:
                    tid = await _dispatch_highest_priority_task(node["node_id"], node.get("address", "127.0.0.1"))
                    if tid is None:
                        break   # no more pending tasks this cycle
                    dispatched_ids.append(tid)
                if dispatched_ids:
                    dispatched_task_id = dispatched_ids[0]
                    cnt = len(dispatched_ids)
                    strategy_text = f"⚡ DISPATCHING{tag} → {cnt} node{'s' if cnt > 1 else ''}"
                elif not idle_nodes:
                    strategy_text = "DEFERRING — No Idle Nodes Available"
                    action = 0
                else:
                    strategy_text = "DEFERRING — Nodes Busy With Tasks"
                    action = 0
            
            # Explainable AI Decision Logging
            reason = explain_decision(action, state_vector, q_values, nodes, carbon_gco2, clean_window_min)

            # Real carbon savings: measured baseline-vs-GridMind emissions across all
            # completed tasks (see app.carbon.ledger). Zero until tasks actually run.
            ledger = carbon_ledger.snapshot()
            savings_pct = ledger["saved_pct"]

            # Audit log. Use the task we actually dispatched (no redundant re-SELECT,
            # which previously logged the wrong task due to the ORM ordering bug).
            if total_pending > 0:
                try:
                    task_id_log = dispatched_task_id or "queue_action"
                    async with AsyncSessionLocal() as db:
                        # Raw-string execute() auto-commits — no extra commit needed.
                        await db.execute(
                            "INSERT INTO dispatch_log (task_id, action, reason, carbon, q_values, ts) "
                            "VALUES (?,?,?,?,?,?)",
                            (task_id_log, "dispatch" if action == 1 else "defer", reason, carbon_gco2, str(q_values), datetime.datetime.now(datetime.timezone.utc).isoformat())
                        )
                except Exception as exc:
                    logger.warning("Failed to log dispatch decision: %s", exc)
            
            # ── 7. Broadcast to dashboard ──────────────────────────────────────
            await ws_manager.broadcast({
                "type":                  "dispatcher_update",
                "queue_size":            total_pending,
                "target_action":         action,
                "strategy":              strategy_text,
                "carbon_savings":        f"{savings_pct:.0f}%",
                "carbon_intensity":      carbon_norm,
                "carbon_gco2":           carbon_gco2,
                "idle_nodes":            len(idle_nodes),
                "total_nodes":           len(nodes),
                "reason":                reason,
                "action_str":            "dispatch" if action == 1 else "defer",
                "q_values":              q_values,
                "override":              override,   # null | "urgent" | "clean-grid" guardrail
                # ── Real carbon-savings ledger (baseline vs GridMind) ──
                "carbon_baseline_g":     ledger["baseline_g"],
                "carbon_gridmind_g":     ledger["gridmind_g"],
                "carbon_saved_g":        ledger["saved_g"],
                "carbon_saved_pct":      ledger["saved_pct"],
                "carbon_tasks_counted":  ledger["tasks_counted"],
                # ── 2-hour grid outlook (real replayed CAISO trajectory) ──
                "carbon_forecast":       carbon_forecast,
                "clean_window_min":      clean_window_min,
            })

            logger.info(
                "[Dispatcher] action=%d queue=%d carbon=%.3f  %s",
                action, total_pending, carbon_gco2, strategy_text,
            )

        except asyncio.CancelledError:
            logger.info("Dispatcher loop cancelled.")
            return
        except Exception as exc:
            logger.error("Dispatcher loop error: %s", exc, exc_info=True)
