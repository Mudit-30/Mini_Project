"""
gridmind_server.app.routes.tasks
==================================
REST endpoints for the GridMind Task Queue.

Endpoints
---------
POST /api/v1/tasks
    Submit a new compute task. Returns the created task record.

GET /api/v1/tasks
    List all tasks (optionally filtered by status).

GET /api/v1/tasks/{task_id}
    Get a single task by ID.

DELETE /api/v1/tasks/{task_id}
    Cancel a pending task.
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import TaskRecord, get_db

router = APIRouter(prefix="/api/v1/tasks", tags=["Tasks"])


# ── Pydantic Schemas ────────────────────────────────────────────────────────────

class TaskSubmit(BaseModel):
    name:     str            = Field(...,   min_length=1, max_length=255,
                                     example="Train ResNet Epoch 5")
    command:  Optional[str]  = Field(None,  example="python train.py --epochs 5")
    priority: int            = Field(5,    ge=1, le=10,
                                     description="1 = highest priority, 10 = lowest")


class TaskOut(BaseModel):
    id:             int
    name:           str
    command:        Optional[str]
    priority:       int
    status:         str
    assigned_node:  Optional[str]
    submitted_at:   Optional[str]
    dispatched_at:  Optional[str]
    completed_at:   Optional[str]
    result_summary: Optional[str]


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _task_out(t: TaskRecord) -> dict[str, Any]:
    return t.to_dict()


# ── Routes ──────────────────────────────────────────────────────────────────────

@router.post("", status_code=201, summary="Submit a new compute task to the queue")
async def submit_task(
    payload: TaskSubmit,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Adds a new task to the pending queue.  The Dispatcher AI will pick it up
    during the next scheduling cycle and assign it to a safe idle node.
    """
    task = TaskRecord(
        name=payload.name,
        command=payload.command,
        priority=payload.priority,
        status="pending",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return {"message": "Task queued successfully.", "task": _task_out(task)}


@router.get("", summary="List all tasks (optionally filter by status)")
async def list_tasks(
    status: Optional[str] = Query(None, examples=["pending", "dispatched", "completed", "failed"],
                                  description="Filter by status: pending, dispatched, completed, failed"),
    limit:  int           = Query(50,   ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Returns tasks ordered by priority ASC, submitted_at ASC (highest priority first)."""
    stmt = select(TaskRecord).order_by(TaskRecord.priority, TaskRecord.submitted_at)
    if status:
        stmt = stmt.where(TaskRecord.status == status)
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    tasks = result.scalars().all()

    # Also return pending count for the dashboard
    count_stmt = select(func.count(TaskRecord.id)).where(TaskRecord.status == "pending")
    pending_count = (await db.execute(count_stmt)).scalar_one()

    return {
        "total": len(tasks),
        "pending_count": pending_count,
        "tasks": [_task_out(t) for t in tasks],
    }


@router.get("/{task_id}", summary="Get a single task by ID")
async def get_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    task = await db.get(TaskRecord, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")
    return _task_out(task)


@router.delete("/{task_id}", summary="Cancel a pending task")
async def cancel_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    task = await db.get(TaskRecord, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")
    if task.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel task in '{task.status}' state. Only 'pending' tasks can be cancelled.",
        )
    task.status = "failed"
    task.result_summary = "Cancelled by user."
    task.completed_at = datetime.datetime.now(datetime.timezone.utc)
    await db.commit()
    return {"message": f"Task {task_id} cancelled.", "task": _task_out(task)}
