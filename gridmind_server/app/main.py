"""
gridmind_server.app.main
--------------------------
FastAPI entry point for the GridMind Central Intelligence Server.

Startup sequence (via lifespan):
  1. Create SQLite tables (idempotent).
  2. Load the Observer AI model (ObserverInference singleton).
  3. Start the async gRPC telemetry server (port 50051).
  4. Start APScheduler: Observer AI auto-retrain every 4 hours.

HTTP API:
  GET /api/v1/health         — liveness probe
  GET /api/v1/nodes          — all connected nodes + current state
  GET /api/v1/nodes/safe     — idle nodes safe for task dispatch
  GET /api/v1/nodes/{id}     — single node details
  GET /docs                  — Swagger UI
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from functools import partial

import sys
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, IOError):
        pass

from app.core.config import settings
from app.db.database import create_tables
from app.grpc_server import serve_grpc
from app.ml.observer_inference import ObserverInference
from app.routes.nodes import router as nodes_router
from app.routes.tasks import router as tasks_router
from app.websockets import manager as ws_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gridmind.server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 1. Ensure DB schema exists ─────────────────────────────────────────────
    logger.info("Initialising database…")
    await create_tables()
    logger.info("Database ready.")

    # ── 2. Load Observer AI ────────────────────────────────────────────────────
    logger.info("Loading Observer AI model…")
    observer = ObserverInference()
    app.state.observer = observer
    logger.info("Observer AI ready: %r", observer)

    # ── 2.5 Load Dispatcher AI & Start Live Validation Loop ────────────────────
    dispatcher_task = None  # must be defined before try-block for safe cleanup
    try:
        from app.ml.dispatcher_inference import DispatcherInference
        dispatcher_engine = DispatcherInference()
        logger.info("Dispatcher AI loaded from ONNX.")
        
        from app.jobs.dispatcher_loop import run_dispatcher_loop
        dispatcher_task = asyncio.create_task(
            run_dispatcher_loop(dispatcher_engine), name="dispatcher-loop"
        )
        logger.info("Dispatcher live websocket validation loop started.")
    except Exception as e:
        logger.warning("Dispatcher AI load skipped (model not found or not trained yet): %s", e)


    # ── 3. Start gRPC server ───────────────────────────────────────────────────
    grpc_task = asyncio.create_task(
        serve_grpc(observer), name="grpc-server"
    )
    logger.info("gRPC telemetry server starting on port 50051.")

    # ── 4. Start APScheduler — retrain Observer AI every 4 hours ──────────────
    from app.jobs.retrain import retrain_observer

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        partial(retrain_observer, observer),
        trigger="interval",
        hours=4,
        id="observer-retrain",
        name="Observer AI Auto-Retrain",
        misfire_grace_time=300,   # allow up to 5 min late start
    )
    scheduler.start()
    logger.info("APScheduler started. Observer AI will retrain every 4 hours.")

    logger.info("✅ GridMind Server fully operational.")

    # ── Yield control to FastAPI ───────────────────────────────────────────────
    try:
        yield
    finally:
        # ── Shutdown ──────────────────────────────────────────────────────────
        logger.info("Shutting down GridMind Server…")
        scheduler.shutdown(wait=False)
        if dispatcher_task:
            dispatcher_task.cancel()
        grpc_task.cancel()
        try:
            await grpc_task
        except asyncio.CancelledError:
            pass
        logger.info("GridMind Server shut down cleanly.")


# ── Application ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="GridMind Server",
    description=(
        "Adaptive, Carbon-Aware Distributed Workstation Scheduling System.\n\n"
        "The central intelligence server that receives live telemetry from worker "
        "nodes, classifies their state with the Observer AI, and exposes endpoints "
        "for the Dispatcher AI and the Next.js dashboard."
    ),
    version=settings.VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development, allowing all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(nodes_router)
app.include_router(tasks_router)


# ── Core endpoints ─────────────────────────────────────────────────────────────
@app.get("/", tags=["General"], summary="Root redirection to documentation")
async def root():
    return RedirectResponse(url="/docs")


@app.get("/api/v1/health", tags=["Health"], summary="Server liveness probe")
async def health_check():
    return {
        "status":  "ok",
        "version": settings.VERSION,
        "message": "GridMind Server is running",
    }


@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    """
    WebSocket endpoint for real-time telemetry updates.
    Sends the initial state immediately upon connection.
    """
    from app.registry import node_registry
    await ws_manager.connect(websocket)
    try:
        # Send initial full registry state
        await websocket.send_text(json.dumps({
            "type": "initial_state",
            "nodes": node_registry.all()
        }))
        while True:
            # Just keep connection open, broadcasts are pushed from gRPC handler
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)
        ws_manager.disconnect(websocket)


# ── Dev entry-point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


