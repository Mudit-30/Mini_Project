"""
gridmind_server.app.main
--------------------------
FastAPI entry point for the GridMind Central Intelligence Server.

Startup sequence (via asynccontextmanager lifespan):
  1. Initialise SQLite schema (idempotent create_tables).
  2. Load the Observer AI (ObserverInference singleton).
  3. Load the Dispatcher AI (DispatcherInference) and start the
     dispatcher decision loop as a background asyncio Task.
  4. Start the async gRPC telemetry server on port 50051.
  5. Start APScheduler: Observer AI auto-retrain every 4 hours.

HTTP API:
  GET  /                      — redirects to /docs
  GET  /api/v1/health         — liveness probe
  GET  /api/v1/nodes          — all connected nodes + current state
  GET  /api/v1/nodes/safe     — idle nodes safe for task dispatch
  GET  /api/v1/nodes/{id}     — single node details
  POST /api/v1/tasks          — submit a compute task
  GET  /api/v1/tasks          — list tasks
  GET  /api/v1/tasks/{id}     — single task by UUID
  DELETE /api/v1/tasks/{id}   — cancel a pending task
  WS   /ws/telemetry          — real-time telemetry + dispatcher events

  GET  /docs                  — Swagger UI
"""
from __future__ import annotations

import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager
from functools import partial

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

# ── Windows UTF-8 console fix ─────────────────────────────────────────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, IOError):
        pass
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

from app.core.config import settings
from app.db.database import create_tables
from app.grpc_server import serve_grpc
from app.ml.observer_inference import ObserverInference
from app.registry import node_registry
from app.routes.nodes import router as nodes_router
from app.routes.tasks import router as tasks_router
from app.routes.jobs import router as jobs_router
from app.websockets import manager as ws_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gridmind.server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and graceful shutdown of all background services."""

    # ── 1. Database ───────────────────────────────────────────────────────────
    logger.info("Initialising database schema…")
    await create_tables()
    logger.info("Database ready.")

    # ── 2. Observer AI ────────────────────────────────────────────────────────
    logger.info("Loading Observer AI…")
    try:
        observer = ObserverInference()
        app.state.observer = observer
        logger.info("Observer AI ready: %r", observer)
    except Exception as exc:
        logger.error("Observer AI failed to load: %s", exc)
        raise

    # ── 3. Dispatcher AI + decision loop ─────────────────────────────────────
    dispatcher_task: asyncio.Task | None = None
    try:
        from app.ml.dispatcher_inference import DispatcherInference
        from app.jobs.dispatcher_loop import run_dispatcher_loop
        dispatcher_engine = DispatcherInference()
        dispatcher_task = asyncio.create_task(
            run_dispatcher_loop(dispatcher_engine),
            name="dispatcher-loop",
        )
        logger.info("Dispatcher AI loaded. Decision loop started.")
    except FileNotFoundError:
        logger.warning(
            "Dispatcher model not found — run dispatcher_trainer.py first. "
            "Dispatcher loop disabled."
        )
    except Exception as exc:
        logger.warning("Dispatcher AI disabled: %s", exc)

    # ── 4. gRPC server ────────────────────────────────────────────────────────
    grpc_task = asyncio.create_task(serve_grpc(observer), name="grpc-server")
    logger.info("gRPC telemetry server starting on port 50051.")

    # ── 5. APScheduler — Observer AI auto-retrain (OPT-IN) ───────────────────
    # Disabled by default: the only label source is the Observer's OWN predicted
    # labels, so periodic retraining is self-supervised on model output — a
    # feedback loop that can entrench errors rather than correct them. Enable
    # explicitly (with an independent label source in mind) via env var.
    scheduler = None
    if os.environ.get("GRIDMIND_ENABLE_RETRAIN") == "1":
        from app.jobs.retrain import retrain_observer
        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(
            partial(retrain_observer, observer),
            trigger="interval",
            hours=4,
            id="observer-retrain",
            name="Observer AI Auto-Retrain",
            misfire_grace_time=300,
        )
        scheduler.start()
        logger.warning("Observer AI auto-retrain ENABLED (self-supervised on predicted labels — see retrain.py).")
    else:
        logger.info("Observer AI auto-retrain disabled (set GRIDMIND_ENABLE_RETRAIN=1 to enable).")
    logger.info("✅ GridMind Server fully operational.")

    # ── Hand control to FastAPI ───────────────────────────────────────────────
    try:
        yield
    finally:
        logger.info("Shutting down GridMind Server…")
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        if dispatcher_task and not dispatcher_task.done():
            dispatcher_task.cancel()
            try:
                await dispatcher_task
            except asyncio.CancelledError:
                pass
        grpc_task.cancel()
        try:
            await grpc_task
        except asyncio.CancelledError:
            pass
        logger.info("GridMind Server shut down cleanly.")


# ── FastAPI application ────────────────────────────────────────────────────────
app = FastAPI(
    title="GridMind Server",
    description=(
        "Adaptive, Carbon-Aware Distributed Workstation Scheduling System.\n\n"
        "Central intelligence server that receives live telemetry from worker "
        "nodes, classifies their state with the Observer AI (Random Forest + temporal "
        "smoothing), and dispatches tasks with the Dueling Double DQN Dispatcher AI."
    ),
    version=settings.VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Lock down in production with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(nodes_router)
app.include_router(tasks_router)
app.include_router(jobs_router)


# ── Core endpoints ─────────────────────────────────────────────────────────────
@app.get("/", tags=["General"], summary="Redirect to API documentation",
         include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")


@app.get("/api/v1/health", tags=["Health"], summary="Server liveness probe")
async def health_check():
    """Quick liveness check — returns 200 when the server is operational."""
    return {
        "status":  "ok",
        "version": settings.VERSION,
        "nodes_online": len(node_registry),
        "message": "GridMind Server is operational.",
    }


@app.get("/api/v1/observer/metadata", tags=["Observer"],
         summary="Observer AI evaluation metadata (held-out accuracy + confusion matrix)")
async def observer_metadata():
    """Return the trained Observer's honest evaluation metrics for the dashboard."""
    from pathlib import Path
    meta_path = Path(__file__).parents[2] / "models" / "observer" / "model_metadata.json"
    try:
        with meta_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {"error": "Observer model not trained yet."}


@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    """
    WebSocket endpoint for real-time telemetry and dispatcher events.
    Sends the full registry state immediately upon connection, then
    listens for pings to keep the connection alive (broadcasts are
    pushed from the gRPC handler and dispatcher loop).
    """
    await ws_manager.connect(websocket)
    try:
        # Push current state immediately on connect
        await websocket.send_text(json.dumps({
            "type":  "initial_state",
            "nodes": node_registry.all(),
        }))
        while True:
            # Keep connection alive by reading (client can send pings)
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as exc:
        logger.warning("WebSocket error: %s", exc)
        ws_manager.disconnect(websocket)


# ── Dev entry-point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
