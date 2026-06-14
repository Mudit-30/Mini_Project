"""
gridmind_server.app.routes.jobs
================================
Data-parallel "jobs": one script fanned out into N chunk-tasks that share a
parent_job_id. Each chunk runs the SAME script over its own slice, told which
slice via the GRIDMIND_CHUNK_INDEX / GRIDMIND_CHUNK_COUNT env vars the node sets.

Chunks are ordinary tasks, so they ride the normal dispatch path — power-aware
node selection, fault-tolerant re-queue, and the carbon ledger all apply. The
dispatcher fans them out one-per-free-node, so on N nodes they run concurrently.
"""
from __future__ import annotations

import datetime
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.db.database import AsyncSession, TaskRecord, get_db
from app.carbon.ledger import get_current_carbon

router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs"])

VALID_PRIORITIES = {"urgent", "deferrable", "best_effort"}


class JobSubmit(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, examples=["Prime Count"])
    script: str = Field(..., min_length=1)
    chunks: int = Field(4, ge=1, le=64, description="Number of parallel chunks to split into")
    priority_str: str = Field("urgent", description="urgent runs immediately across free nodes")

    @field_validator("priority_str")
    @classmethod
    def _validate(cls, v: str) -> str:
        if v not in VALID_PRIORITIES:
            raise ValueError(f"Invalid priority '{v}'. Must be one of {sorted(VALID_PRIORITIES)}")
        return v


def _parse(ts: str | None) -> datetime.datetime | None:
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(ts)
    except Exception:
        return None


@router.post("", status_code=201, summary="Submit a data-parallel job (split into N chunks)")
async def submit_job(payload: JobSubmit, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Create N chunk-tasks; the dispatcher fans them out across free idle nodes."""
    job_id = str(uuid.uuid4())
    carbon = get_current_carbon()
    tasks = [
        TaskRecord(
            task_id=str(uuid.uuid4()),
            name=payload.name,
            script=payload.script,
            priority_str=payload.priority_str,
            status="pending",
            parent_job_id=job_id,
            chunk_index=i,
            chunk_count=payload.chunks,
            submit_carbon_gco2=carbon,
        )
        for i in range(payload.chunks)
    ]
    db.add_all(tasks)
    await db.commit()
    return {
        "message": f"Job '{payload.name}' split into {payload.chunks} chunks.",
        "job_id": job_id,
        "chunk_count": payload.chunks,
    }


@router.get("", summary="List recent parallel jobs")
async def list_jobs(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    cur = await db.execute(
        "SELECT parent_job_id AS job_id, MAX(name) AS name, MAX(chunk_count) AS chunk_count, "
        "MIN(submitted_at) AS submitted_at, "
        "SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed, "
        "SUM(CASE WHEN status IN ('failed','aborted','cancelled') THEN 1 ELSE 0 END) AS failed, "
        "COUNT(*) AS total "
        "FROM tasks WHERE parent_job_id IS NOT NULL "
        "GROUP BY parent_job_id ORDER BY MIN(submitted_at) DESC LIMIT 10"
    )
    jobs = [dict(r) for r in await cur.fetchall()]
    return {"jobs": jobs}


@router.get("/{job_id}", summary="Get a parallel job's chunks + measured speedup")
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    cur = await db.execute(
        "SELECT task_id, chunk_index, chunk_count, status, assigned_node, duration_secs, "
        "dispatched_at, completed_at, name FROM tasks WHERE parent_job_id=? ORDER BY chunk_index",
        (job_id,),
    )
    rows = [dict(r) for r in await cur.fetchall()]
    if not rows:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    chunk_count = rows[0]["chunk_count"]
    terminal = {"completed", "failed", "aborted", "cancelled"}
    done = [r for r in rows if r["status"] == "completed"]
    all_done = len(rows) == chunk_count and all(r["status"] in terminal for r in rows)

    nodes_used = sorted({r["assigned_node"] for r in done if r["assigned_node"]})
    serial_secs = wall_secs = speedup = None
    if all_done and done:
        # serial = sum of chunk compute (what one node would take, back-to-back).
        # wall   = actual elapsed (first dispatch → last completion). On N nodes the
        # chunks overlap so wall ≈ longest chunk → speedup ≈ N. We only report a
        # speedup multiplier when ≥2 nodes actually shared the work — on a single
        # node chunks run sequentially (plus dispatch-cycle gaps), so a multiplier
        # would be meaningless/misleading.
        serial_secs = round(sum((r["duration_secs"] or 0.0) for r in done), 2)
        starts = [d for d in (_parse(r["dispatched_at"]) for r in done) if d]
        ends = [d for d in (_parse(r["completed_at"]) for r in done) if d]
        if starts and ends:
            wall_secs = round((max(ends) - min(starts)).total_seconds(), 2)
            if wall_secs and wall_secs > 0 and len(nodes_used) >= 2:
                speedup = round(serial_secs / wall_secs, 2)

    return {
        "job_id": job_id,
        "name": rows[0]["name"],
        "chunk_count": chunk_count,
        "completed": len(done),
        "total": len(rows),
        "all_done": all_done,
        "serial_secs": serial_secs,
        "wall_secs": wall_secs,
        "speedup": speedup,
        "nodes_used": nodes_used,
        "chunks": [
            {
                "chunk_index": r["chunk_index"],
                "status": r["status"],
                "assigned_node": r["assigned_node"],
                "duration_secs": r["duration_secs"],
            }
            for r in rows
        ],
    }
