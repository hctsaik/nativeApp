"""
routers/tasks.py — All /tasks and /admin/tasks endpoints for the iWISC service.
"""

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_connection

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ResultPayload(BaseModel):
    platform_task_id: str | None = None
    annotation_json: Any = None
    new_classification: str | None = None
    annotated_by: str | None = None


class AntTaskDetailRequest(BaseModel):
    antID: str
    format: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_task_dict(row) -> dict:
    """Convert a sqlite3.Row from iwsc_tasks into the public task shape."""
    return {
        "antID": row["ant_id"],
        "antActive": row["ant_active"],
        "antPeriod": row["ant_period"],
        "external_context": json.loads(row["external_context"]) if row["external_context"] else {},
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# GET /tasks — return all pending tasks (ant_active = 0)
# ---------------------------------------------------------------------------

def _fetch_pending_tasks():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM iwsc_tasks WHERE ant_active = 0 ORDER BY ant_period"
        ).fetchall()
        return [_row_to_task_dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/tasks", summary="Get pending tasks (ant_active=0)")
def list_pending_tasks():
    return _fetch_pending_tasks()


@router.get("/getAntList", summary="CIM platform compat alias for GET /tasks")
def get_ant_list():
    """Alias endpoint matching CIM RestConnector's expected path."""
    return _fetch_pending_tasks()


# ---------------------------------------------------------------------------
# POST /getAntTaskDetail — CIM platform compat: return task ZIP download URL
# ---------------------------------------------------------------------------

@router.post("/getAntTaskDetail", summary="Return task detail (ZIP URL) for a given antID")
def get_ant_task_detail(body: AntTaskDetailRequest):
    """
    CIM platform calls this after claiming a task to get the ZIP download URL.
    iWISC does not generate image ZIPs, so download_url is null — the platform
    will skip the download step and create an empty annotation task.
    """
    conn = get_connection()
    try:
        task = conn.execute(
            "SELECT * FROM iwsc_tasks WHERE ant_id = ?", (body.antID,)
        ).fetchone()
        if task is None:
            raise HTTPException(status_code=404, detail=f"Task {body.antID!r} not found")
        return {"antID": body.antID, "download_url": None}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# POST /tasks/{ant_id}/result — receive annotation result from platform
# ---------------------------------------------------------------------------

@router.post("/tasks/{ant_id}/result", summary="Receive annotation result from platform")
def submit_result(ant_id: str, payload: ResultPayload):
    conn = get_connection()
    try:
        task = conn.execute(
            "SELECT * FROM iwsc_tasks WHERE ant_id = ?", (ant_id,)
        ).fetchone()

        if task is None:
            raise HTTPException(status_code=404, detail=f"Task {ant_id!r} not found")

        now = _utc_now()

        # Insert result record
        conn.execute(
            """
            INSERT INTO iwsc_results
                (ant_id, platform_task_id, annotation_json, new_classification, annotated_by, received_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                ant_id,
                payload.platform_task_id,
                json.dumps(payload.annotation_json) if payload.annotation_json is not None else None,
                payload.new_classification,
                payload.annotated_by,
                now,
            ),
        )

        # Mark task as completed (ant_active = 2)
        conn.execute(
            "UPDATE iwsc_tasks SET ant_active = 2, updated_at = ? WHERE ant_id = ?",
            (now, ant_id),
        )
        conn.commit()

        return {"status": "ok", "ant_id": ant_id, "received_at": now}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /tasks/{ant_id}/result — retrieve stored result (debug)
# ---------------------------------------------------------------------------

@router.get("/tasks/{ant_id}/result", summary="Get stored result for a task (debug)")
def get_result(ant_id: str):
    conn = get_connection()
    try:
        task = conn.execute(
            "SELECT ant_id FROM iwsc_tasks WHERE ant_id = ?", (ant_id,)
        ).fetchone()
        if task is None:
            raise HTTPException(status_code=404, detail=f"Task {ant_id!r} not found")

        rows = conn.execute(
            "SELECT * FROM iwsc_results WHERE ant_id = ? ORDER BY received_at DESC",
            (ant_id,),
        ).fetchall()

        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /admin/tasks — return ALL tasks regardless of ant_active (debug)
# ---------------------------------------------------------------------------

@router.get("/admin/tasks", summary="List all tasks with any status (admin/debug)")
def admin_list_tasks():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM iwsc_tasks ORDER BY ant_period"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
