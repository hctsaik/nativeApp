"""
module_009 process layer — no Streamlit imports.

Public API:
  scan_folder(folder_path)              -> list[dict]
  load_assets(db_path)                  -> list[dict]
  start_annotation(session_id, anchor_info) -> dict
  open_xanylabeling(session_id)         -> dict
  open_labeling_tool(session_id, tool)  -> dict
  open_single_frame(session_id, frame_idx) -> dict
  get_session_status(session_id)        -> dict | None
  update_after_xany_close(session_id)   -> dict
  sync_to_db(session_ids)               -> dict
  get_next_unannotated(db_path)         -> int | None
  generate_summary(session_id)          -> dict
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _db as db
import _xany_launcher as launcher
from _config import get_db_path


_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_XANY_BASE = _PROJECT_ROOT / "tmp" / "cim_log" / "annotation-sessions"


def _db_path() -> Path:
    return get_db_path()


def _xany_project_dir(session_id: int) -> Path:
    base = Path(os.environ.get("CIM_LOG_DIR", _PROJECT_ROOT / "tmp" / "cim_log"))
    return base / "annotation-sessions" / f"session_{session_id:04d}"


# ── Asset management ───────────────────────────────────────────────────────────

def scan_folder(folder_path: str) -> list[dict]:
    return db.scan_folder(_db_path(), folder_path)


def load_assets(db_path_override: Optional[str] = None) -> list[dict]:
    p = Path(db_path_override) if db_path_override else _db_path()
    return db.load_assets(p)


# ── Session lifecycle ──────────────────────────────────────────────────────────

def start_annotation(session_id: int, anchor_info: dict) -> dict:
    """
    For video assets: write anchor_info, set status='追蹤中', launch _worker.py.
    For image_dir assets: copy images to frames/, set status='標記中', open X-AnyLabeling directly.
    """
    import shutil
    import sqlite3 as _sqlite3

    dp = _db_path()
    session = db.get_session_status(dp, session_id)
    if not session:
        return {"ok": False, "error": "Session not found"}

    # Look up asset_type
    conn = _sqlite3.connect(str(dp))
    conn.row_factory = _sqlite3.Row
    asset = conn.execute(
        "SELECT * FROM video_assets WHERE id=?", (session["asset_id"],)
    ).fetchone()
    conn.close()
    if not asset:
        return {"ok": False, "error": "Asset not found"}

    xany_dir = _xany_project_dir(session_id)
    xany_dir.mkdir(parents=True, exist_ok=True)

    (xany_dir / "anchor_info.json").write_text(
        json.dumps(anchor_info, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    db.update_session(dp, session_id, xany_project_dir=str(xany_dir))

    if asset["asset_type"] == "image_dir":
        # For image directories: copy images to frames/, skip tracking worker
        frames_dir = xany_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
        src_folder = Path(asset["file_path"])
        images = sorted(f for f in src_folder.iterdir() if f.suffix.lower() in image_exts)
        for idx, img in enumerate(images):
            dest = frames_dir / f"frame_{idx:06d}.jpg"
            if not dest.exists():
                shutil.copy2(str(img), str(dest))
        db.update_session(dp, session_id, status="標記中")
        return {"ok": True, "session_id": session_id, "asset_type": "image_dir", "tracking_pid": None}

    # Video: launch DINOv2+LK tracking worker
    db.update_session(dp, session_id, status="追蹤中")
    pid = launcher.start_tracking_worker(dp, session_id)
    db.update_session(dp, session_id, tracking_job_pid=pid)
    return {"ok": True, "session_id": session_id, "asset_type": "video", "tracking_pid": pid}


def open_xanylabeling(session_id: int) -> dict:
    return launcher.open_xanylabeling(_db_path(), session_id)


def open_labeling_tool(session_id: int, tool: str = "x-anylabeling") -> dict:
    normalized = (tool or "x-anylabeling").strip().lower().replace("_", "-")
    if normalized in {"xanylabeling", "x-anylabeling"}:
        return open_xanylabeling(session_id)
    return {
        "ok": False,
        "error": f"module_009 tracking correction currently supports launch automation for x-anylabeling only; requested {tool}",
        "tool": normalized,
        "xany_pid": None,
    }


def open_single_frame(session_id: int, frame_idx: int) -> dict:
    return launcher.open_single_frame(_db_path(), session_id, frame_idx)


def get_session_status(session_id: int) -> Optional[dict]:
    return db.get_session_status(_db_path(), session_id)


def update_after_xany_close(session_id: int) -> dict:
    return launcher.update_after_xany_close(_db_path(), session_id)


def update_after_labeling_close(session_id: int, tool: str = "x-anylabeling") -> dict:
    normalized = (tool or "x-anylabeling").strip().lower().replace("_", "-")
    if normalized in {"xanylabeling", "x-anylabeling"}:
        return update_after_xany_close(session_id)
    return {"ok": False, "error": f"Unsupported module_009 sync tool: {tool}", "tool": normalized}


def update_after_single_close(session_id: int, frame_idx: int) -> dict:
    dp = _db_path()
    session = db.get_session_status(dp, session_id)
    if not session or not session["xany_project_dir"]:
        return {"ok": False, "error": "Session or xany_project_dir not found"}
    single_ann_dir = Path(session["xany_project_dir"]) / "single_frame_correction"
    return launcher.update_after_single_close(dp, session_id, frame_idx, single_ann_dir)


def sync_to_db(session_ids: list[int]) -> dict:
    return launcher.sync_to_db(_db_path(), session_ids)


# ── Utilities ──────────────────────────────────────────────────────────────────

def get_next_unannotated(db_path_override: Optional[str] = None) -> Optional[int]:
    p = Path(db_path_override) if db_path_override else _db_path()
    return db.get_next_unannotated(p)


def generate_summary(session_id: int) -> dict:
    return db.generate_summary(_db_path(), session_id)


def poll_tracking_status(session_id: int) -> dict:
    """
    Check if tracking worker is done (status flipped to '標記中') and
    auto-launch X-AnyLabeling if so. Called by the UI poll loop.
    """
    session = get_session_status(session_id)
    if not session:
        return {"status": "unknown"}
    status = session["status"]
    if status == "標記中" and session.get("xany_pid") is None:
        result = open_labeling_tool(session_id, "x-anylabeling")
        if result.get("ok"):
            return {"status": "xany_launched", "result": result}
        return {"status": "xany_launch_failed", "error": result.get("error")}
    return {"status": status}
