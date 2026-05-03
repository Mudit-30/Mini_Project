import asyncio
import logging
import math
import datetime
import os
import pandas as pd

from sqlalchemy import select, func, update
from app.db.database import AsyncSessionLocal, TaskRecord
from app.registry import node_registry
from app.websockets import manager as ws_manager

logger = logging.getLogger("gridmind.dispatcher")

# Load Real Carbon Data
CARBON_SERIES = []
try:
    csv_path = os.path.join(os.path.dirname(__file__), "../../../watttime_carbon_data_CAISO_NORTH.csv")
    df = pd.read_csv(os.path.abspath(csv_path))
    min_c = df['value'].min()
    max_c = df['value'].max()
    CARBON_SERIES = ((df['value'] - min_c) / (max_c - min_c)).values.tolist()
    logger.info(f"Loaded {len(CARBON_SERIES)} real carbon data points from CAISO NORTH.")
except Exception as e:
    logger.error(f"Failed to load real carbon data, falling back to math.sin: {e}")

# State → integer mapping, kept consistent with dispatcher_env.py
_STATE_MAP = {"idle": 0, "active_user": 1, "busy_hardware": 2}


async def _get_pending_count() -> int:
    """Query the real task queue for pending task count."""
    try:
        async with AsyncSessionLocal() as db:
            stmt = select(func.count(TaskRecord.id)).where(TaskRecord.status == "pending")
            return (await db.execute(stmt)).scalar_one()
    except Exception:
        return 0


async def _dispatch_task_to_node(node_id: str) -> None:
    """
    Mark the highest-priority pending task as dispatched to the given node.
    Orders by priority ASC (1=highest), then submitted_at ASC (FIFO).
    """
    try:
        async with AsyncSessionLocal() as db:
            stmt = (
                select(TaskRecord)
                .where(TaskRecord.status == "pending")
                .order_by(TaskRecord.priority, TaskRecord.submitted_at)
                .limit(1)
            )
            result = await db.execute(stmt)
            task = result.scalar_one_or_none()
            if task:
                task.status = "dispatched"
                task.assigned_node = node_id
                task.dispatched_at = datetime.datetime.now(datetime.timezone.utc)
                await db.commit()
                logger.info("Task '%s' (id=%d) dispatched to node '%s'", task.name, task.id, node_id)
    except Exception as e:
        logger.error("Failed to dispatch task: %s", e)


async def run_dispatcher_loop(inference_engine):
    """
    Background job that runs every 2 seconds:
    1. Reads the REAL pending task count from SQLite.
    2. Reads live node states from the in-memory registry.
    3. Builds a smooth sine-wave carbon trace (mimics real grid patterns).
    4. Queries the DQN inference engine for the optimal action.
    5. If action = DISPATCH, marks the top-priority task as dispatched.
    6. Broadcasts the decision to all connected Next.js dashboard clients.
    """
    logger.info("Dispatcher Live Validation Loop started.")
    step = 0  # used for smooth sine-based carbon oscillation

    while True:
        await asyncio.sleep(2)
        step += 1

        try:
            # 1. Real pending task count from DB
            queue_size = await _get_pending_count()

            # 2. Fetch live node states from the registry
            nodes = node_registry.all()
            node_states = [0, 0, 0]
            for i, n in enumerate(nodes[:3]):
                raw_state = n.get("state", "idle")
                node_states[i] = _STATE_MAP.get(raw_state, 0)

            # 3. Real Carbon Intensity from WattTime historical dataset
            if CARBON_SERIES:
                carbon_intensity = CARBON_SERIES[step % len(CARBON_SERIES)]
                carbon_intensity = round(carbon_intensity, 4)
            else:
                carbon_intensity = 0.5 + 0.35 * math.sin(step * 2 * math.pi / 90)
                carbon_intensity = round(max(0.0, min(1.0, carbon_intensity)), 4)

            # 4. Query Dispatcher AI
            state_vector = [float(queue_size), carbon_intensity] + [float(s) for s in node_states]
            action = inference_engine.predict_action(state_vector)

            # 5. Convert action to human-readable strategy
            idle_nodes = [
                nodes[i].get("node_id", f"Node {i+1}")
                for i in range(min(len(nodes), 3))
                if node_states[i] == 0
            ]

            if action == 0:
                if queue_size == 0:
                    strategy_text = "IDLE — Queue Empty"
                elif carbon_intensity > 0.65:
                    strategy_text = f"DEFERRING — Grid Carbon High ({carbon_intensity:.0%})"
                elif not idle_nodes:
                    strategy_text = "DEFERRING — All Nodes Busy"
                else:
                    strategy_text = "DEFERRING — AI Strategising"
            else:
                target_idx = action - 1
                if target_idx < len(nodes):
                    node_name = nodes[target_idx].get("node_id", f"Node {target_idx + 1}")
                else:
                    node_name = f"Node {target_idx + 1}"
                strategy_text = f"⚡ DISPATCHING → {node_name}"

                # 5a. Actually mark the task as dispatched in the DB
                if queue_size > 0:
                    await _dispatch_task_to_node(node_name)

            carbon_savings_pct = int((1.0 - carbon_intensity) * 100)

            # 6. Broadcast to dashboard
            payload = {
                "type":             "dispatcher_update",
                "queue_size":       queue_size,
                "target_action":    action,
                "strategy":         strategy_text,
                "carbon_savings":   f"{carbon_savings_pct}%",
                "carbon_intensity": carbon_intensity,
            }
            await ws_manager.broadcast(payload)

            logger.debug(
                "[Dispatcher] action=%d strategy=%r queue=%d carbon=%.2f",
                action, strategy_text, queue_size, carbon_intensity,
            )

        except Exception as e:
            logger.error("Dispatcher loop error: %s", e, exc_info=True)
