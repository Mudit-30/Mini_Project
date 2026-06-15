"""
gridmind_server.app.routes.tasks
==================================
REST endpoints for the GridMind Task Queue.

Endpoints
---------
POST /api/v1/tasks
    Submit a new compute task. Returns the created task record.

GET /api/v1/tasks
    List all tasks (optionally filtered by status), ordered by
    priority (urgent first) then submission time (FIFO within tier).

GET /api/v1/tasks/{task_id}
    Get a single task by UUID string (not integer PK).

DELETE /api/v1/tasks/{task_id}
    Cancel a pending task (sets status to "cancelled").

Notes
-----
- task_id is a UUID string (36 chars).  The URL parameter is now a string
  to avoid confusion with the integer PK ``id``.
- Priority validation ensures only the three accepted strings are stored.
"""
from __future__ import annotations

import datetime
import os
import sys
import shutil
import uuid
import hashlib
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from app.db.database import TaskRecord, get_db, select, func, update, AsyncSession
from app.carbon.ledger import get_current_carbon

router = APIRouter(prefix="/api/v1/tasks", tags=["Tasks"])

# Valid priority values
VALID_PRIORITIES = {"urgent", "deferrable", "best_effort"}

# Artifact storage directories
ARTIFACTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "artifacts"))
os.makedirs(os.path.join(ARTIFACTS_DIR, "in"), exist_ok=True)
os.makedirs(os.path.join(ARTIFACTS_DIR, "out"), exist_ok=True)


# ── Pydantic Schemas ───────────────────────────────────────────────────────────

class TaskSubmit(BaseModel):
    name:         str = Field(..., min_length=1, max_length=255,
                              examples=["Train ResNet Epoch 5"])
    script:       str = Field(..., min_length=1,
                              examples=["import time; time.sleep(2); print('done')"])
    priority_str: str = Field(
        "deferrable",
        description="One of: urgent | deferrable | best_effort",
        examples=["urgent"],
    )

    @field_validator("priority_str")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        if v not in VALID_PRIORITIES:
            raise ValueError(
                f"Invalid priority '{v}'. Must be one of: {sorted(VALID_PRIORITIES)}"
            )
        return v


class TaskOut(BaseModel):
    id:            int
    task_id:       str
    name:          str
    script:        str
    priority_str:  str
    status:        str
    assigned_node: Optional[str] = None
    submitted_at:  Optional[str] = None
    dispatched_at: Optional[str] = None
    completed_at:  Optional[str] = None
    stdout:        Optional[str] = None
    stderr:        Optional[str] = None
    exit_code:     Optional[int] = None
    duration_secs: Optional[float] = None
    has_artifact:  bool = False
    artifact_path: Optional[str] = None
    output_artifact_path: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _serialize(task: TaskRecord) -> dict[str, Any]:
    return task.to_dict()


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("", status_code=201, summary="Submit a new compute task to the queue")
async def submit_task(
    payload: TaskSubmit,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Add a new task to the pending queue.  The Dispatcher AI will pick it up
    during the next scheduling cycle and assign it to a safe idle node.
    """
    # Hash kept for reference/auditing. NOTE: we intentionally do NOT short-circuit
    # to a cached completed task here — re-submitting the same script must queue a
    # fresh run (otherwise a repeat demo submission would silently never dispatch).
    script_md5 = hashlib.md5(payload.script.encode("utf-8")).hexdigest()

    task = TaskRecord(
        task_id     = str(uuid.uuid4()),
        name        = payload.name,
        script      = payload.script,
        priority_str= payload.priority_str,
        status      = "pending",
        script_md5  = script_md5,
        # Stamp the grid intensity now — this is what a naive "run immediately"
        # scheduler would have emitted at. The carbon ledger uses it as baseline.
        submit_carbon_gco2 = get_current_carbon(),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    
    # Visual Terminal Notification for Demo
    if sys.platform == "win32":
        try:
            with open("CONOUT$", "w", encoding="utf-8") as con:
                con.write(f"\n[🚀 NOTIFICATION] Task Received: {payload.name}\n")
        except Exception:
            pass
            
    return {"message": "Task queued successfully.", "task": _serialize(task)}


@router.get("", summary="List all tasks (optionally filter by status)")
async def list_tasks(
    status: Optional[str] = Query(
        None,
        description="Filter: pending | dispatched | running | completed | failed | cancelled",
    ),
    limit: int = Query(50, ge=1, le=500, description="Max results to return"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Returns tasks newest-first (most recently submitted at the top). This is the
    "Recent Tasks" view, so a just-submitted task always appears immediately —
    ordering by priority here would push a new low-priority (or any) task below
    the limit window when many tasks exist. (Dispatch order is decided separately
    in the dispatcher loop, not by this display query.)
    """
    stmt = (
        select(TaskRecord)
        .order_by(TaskRecord.submitted_at.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(TaskRecord.status == status)

    tasks = (await db.execute(stmt)).scalars().all()

    pending_count = (
        await db.execute(
            select(func.count(TaskRecord.id)).where(TaskRecord.status == "pending")
        )
    ).scalar_one()

    return {
        "total":         len(tasks),
        "pending_count": pending_count,
        "tasks":         [_serialize(t) for t in tasks],
    }


@router.get("/{task_id}", summary="Get a single task by UUID")
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Look up a task by its UUID string (the ``task_id`` field, not the
    integer ``id``).  Returns 404 if the task does not exist.
    """
    result = await db.execute(
        select(TaskRecord).where(TaskRecord.task_id == task_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    return _serialize(task)


@router.delete("", summary="Clear all finished (completed/failed/cancelled) tasks from history")
async def clear_finished_tasks(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Bulk-remove every task in a terminal state from history. Active tasks
    (pending/dispatched/running) are left untouched — cancel those individually.
    """
    cur = await db.execute(
        "DELETE FROM tasks WHERE status IN ('completed','failed','cancelled')"
    )
    removed = getattr(cur, "rowcount", 0) or 0
    return {"message": f"Cleared {removed} finished task(s) from history.", "removed": removed}


@router.delete("/{task_id}", summary="Cancel an active task, or remove a finished task from history")
async def cancel_or_remove_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    - If the task is **pending / dispatched / running**: cancel it (abort on node).
    - If the task is **completed / failed / cancelled**: remove it from history.
    """
    result = await db.execute(
        select(TaskRecord).where(TaskRecord.task_id == task_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")

    # Finished task → delete the record from history.
    if task.status in ("completed", "failed", "cancelled"):
        await db.execute("DELETE FROM tasks WHERE task_id=?", (task_id,))
        return {"message": f"Task '{task_id}' removed from history.", "removed": True}

    # Otherwise it is active → cancel it.

    # Try to cancel active gRPC dispatch task if running
    from app.task_dispatcher import cancel_active_task
    await cancel_active_task(task_id)
    
    # Update DB status to cancelled
    from app.db.database import update
    now = datetime.datetime.now(datetime.timezone.utc)
    await db.execute(
        update(TaskRecord)
        .where(TaskRecord.task_id == task_id)
        .values(
            status="cancelled",
            stderr="Cancelled by user request.",
            completed_at=now
        )
    )
    await db.commit()
    
    # Broadcast to dashboard
    from app.websockets import manager as ws_manager
    await ws_manager.broadcast({
        "type":    "task_output",
        "task_id": task_id,
        "status":  "cancelled",
        "stderr":  "Cancelled by user request.",
    })
    
    # Refresh to return accurate state
    result = await db.execute(
        select(TaskRecord).where(TaskRecord.task_id == task_id)
    )
    task = result.scalar_one_or_none()
    return {"message": f"Task '{task_id}' cancelled.", "task": _serialize(task)}


# ── Artifact Routes ────────────────────────────────────────────────────────────

@router.post("/with-artifact", status_code=201, summary="Submit a task with a ZIP workspace")
async def submit_task_with_artifact(
    name: str = Form(...),
    script: str = Form(..., description="Entrypoint script or command to run inside the workspace"),
    priority_str: str = Form("deferrable"),
    file: UploadFile = File(..., description="ZIP file containing the workspace/project"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Submit a task along with a ZIP file containing the full project workspace."""
    if priority_str not in VALID_PRIORITIES:
        from fastapi import HTTPException as _HTTPException
        raise _HTTPException(status_code=422, detail=f"Invalid priority '{priority_str}'. Must be one of: {sorted(VALID_PRIORITIES)}")
    task_id = str(uuid.uuid4())
    
    file_path = os.path.join(ARTIFACTS_DIR, "in", f"{task_id}.zip")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    with open(file_path, "rb") as f:
        file_hash = hashlib.md5(f.read()).hexdigest()
        
    script_md5 = hashlib.md5((script + file_hash).encode("utf-8")).hexdigest()

    # No cache short-circuit (see submit_task) — every submission queues a fresh run.
    task = TaskRecord(
        task_id     = task_id,
        name        = name,
        script      = script,
        priority_str= priority_str,
        status      = "pending",
        has_artifact= 1,
        artifact_path= file_path,
        script_md5  = script_md5,
        submit_carbon_gco2 = get_current_carbon(),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    
    # Visual Terminal Notification for Demo
    if sys.platform == "win32":
        try:
            with open("CONOUT$", "w", encoding="utf-8") as con:
                con.write(f"\n[🚀 NOTIFICATION] File/Workspace Received: {file.filename} (Task: {name})\n")
        except Exception:
            pass
            
    return {"message": "Task queued with artifact.", "task": _serialize(task)}


@router.get("/{task_id}/artifact", summary="Download the input ZIP workspace for a task")
async def download_artifact(task_id: str, db: AsyncSession = Depends(get_db)):
    """Used by the Node Agent to download the ZIP workspace before execution."""
    result = await db.execute(select(TaskRecord).where(TaskRecord.task_id == task_id))
    task = result.scalar_one_or_none()
    if not task or not task.has_artifact or not task.artifact_path:
        raise HTTPException(status_code=404, detail="Artifact not found for this task.")
    return FileResponse(task.artifact_path, filename=f"workspace_{task_id}.zip")


@router.post("/{task_id}/artifact/output", summary="Upload the output ZIP workspace from a task")
async def upload_output_artifact(
    task_id: str, 
    file: UploadFile = File(...), 
    db: AsyncSession = Depends(get_db)
):
    """Used by the Node Agent to upload the results ZIP after execution."""
    result = await db.execute(select(TaskRecord).where(TaskRecord.task_id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
        
    out_path = os.path.join(ARTIFACTS_DIR, "out", f"{task_id}_output.zip")
    with open(out_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Persist via update() — mutating the loaded `task` row + commit() is a no-op
    # in this lightweight ORM (commit only flushes add()-ed rows). This is why
    # artifact download used to always 404.
    await db.execute(
        update(TaskRecord).where(TaskRecord.task_id == task_id).values(output_artifact_path=out_path)
    )
    await db.commit()
    return {"message": "Output uploaded successfully."}


@router.get("/{task_id}/artifact/output", summary="Download the final output ZIP")
async def download_output_artifact(task_id: str, db: AsyncSession = Depends(get_db)):
    """Used by the frontend/user to download the final results of a task."""
    result = await db.execute(select(TaskRecord).where(TaskRecord.task_id == task_id))
    task = result.scalar_one_or_none()
    if not task or not task.output_artifact_path:
        raise HTTPException(status_code=404, detail="Output artifact not found. Task may not be finished.")
    return FileResponse(task.output_artifact_path, filename=f"results_{task_id}.zip")
