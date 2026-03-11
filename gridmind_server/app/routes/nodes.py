"""
gridmind_server.app.routes.nodes
==================================
REST endpoints for querying the live state of connected worker nodes.

Endpoints
---------
GET /api/v1/nodes
    Returns all currently known nodes with their latest telemetry + state.

GET /api/v1/nodes/{node_id}
    Returns the latest telemetry + state for a specific node.

GET /api/v1/nodes/safe
    Returns only nodes whose current state is 'idle' — safe to dispatch tasks.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.registry import node_registry

router = APIRouter(prefix="/api/v1/nodes", tags=["Nodes"])


@router.get("", summary="List all connected nodes and their current state")
async def list_nodes() -> dict[str, Any]:
    """
    Returns every node that has sent at least one telemetry packet since
    the server started, along with its latest observed state.
    """
    nodes = node_registry.all()
    return {
        "count": len(nodes),
        "nodes": nodes,
    }


@router.get("/safe", summary="List idle nodes safe for task dispatch")
async def list_safe_nodes() -> dict[str, Any]:
    """
    Returns node IDs whose latest Observer AI classification is **idle**.
    These are the only nodes the Dispatcher AI should consider for task assignment.
    """
    safe = node_registry.safe_nodes()
    return {
        "count": len(safe),
        "safe_node_ids": safe,
    }


@router.get("/{node_id}", summary="Get the latest state for a specific node")
async def get_node(node_id: str) -> dict[str, Any]:
    """
    Returns the latest telemetry snapshot and Observer AI prediction for
    the requested node. Raises **404** if the node has never connected.
    """
    entry = node_registry.get(node_id)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"Node '{node_id}' not found. It may not have connected yet.",
        )
    return entry
