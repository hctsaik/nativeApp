"""
X-AnyLabeling integration for module_009.

Handles:
  - Starting the tracking worker subprocess
  - Launching X-AnyLabeling with the xany project
  - PID monitoring (background thread)
  - Parsing annotations after X-AnyLabeling closes
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import psutil


_PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _get_xany_exe() -> str:
    candidates = [
        Path(os.environ.get("XANYLABELING_EXE", "")),
        _PROJECT_ROOT / ".venv-xanylabeling" / "Scripts" / "xanylabeling.exe",
    ]
    for c in candidates:
        if str(c) and c.exists():
            return str(c)
    return "xanylabeling"


def _xany_env(exe: str) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONNOUSERSITE"] = "1"
    if exe != "xanylabeling":
        env["PATH"] = str(Path(exe).resolve().parent) + os.pathsep + env.get("PATH", "")
    return env


def _xany_command_prefix(exe: str) -> list[str]:
    exe_path = Path(exe)
    if exe_path.name.lower().startswith("xanylabeling"):
        python = exe_path.parent / "python.exe"
        if python.exists():
            return [str(python), "-m", "anylabeling.app"]
    return [exe]


def _worker_script() -> Path:
    return Path(__file__).resolve().parent / "_worker.py"


def start_tracking_worker(db_path: Path, session_id: int) -> int:
    proc = subprocess.Popen(
        [sys.executable, str(_worker_script()), str(db_path), str(session_id)],
        cwd=str(Path(__file__).resolve().parent),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return proc.pid


def open_xanylabeling(db_path: Path, session_id: int) -> dict:
    """
    Build an X-AnyLabeling project from frame_annotations and launch it.
    Returns {"ok": bool, "error": str | None, "xany_pid": int | None}
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _db as db

    session = db.get_session_status(db_path, session_id)
    if not session:
        return {"ok": False, "error": "Session not found", "xany_pid": None}

    xany_project_dir = Path(session["xany_project_dir"])
    frames_dir = xany_project_dir / "frames"
    ann_dir = xany_project_dir / "annotations"

    # Build classes.txt: prefer existing annotation labels, fallback to anchor_info
    frame_rows = db.get_frame_annotations(db_path, session_id)
    labels: set[str] = set()
    for row in frame_rows:
        try:
            data = json.loads(row["annotation_json"])
            for shape in data.get("shapes", []):
                lbl = shape.get("label", "")
                if lbl:
                    labels.add(lbl)
        except Exception:
            pass
    if not labels:
        anchor_file = xany_project_dir / "anchor_info.json"
        if anchor_file.exists():
            try:
                anchor = json.loads(anchor_file.read_text(encoding="utf-8"))
                for lbl in anchor.get("labels", []):
                    if lbl:
                        labels.add(lbl)
            except Exception:
                pass

    classes_txt = xany_project_dir / "classes.txt"
    if labels:
        classes_txt.write_text("\n".join(sorted(labels)), encoding="utf-8")

    # Open the frames directory so user can browse all frames
    if not frames_dir.exists() or not any(frames_dir.glob("frame_*.jpg")):
        return {"ok": False, "error": f"No frame files in: {frames_dir}", "xany_pid": None}

    xany_work = xany_project_dir / ".xanylabeling"
    exe = _get_xany_exe()
    cmd = _xany_command_prefix(exe) + [
        "--filename", str(frames_dir),
        "--output", str(ann_dir),
        "--work-dir", str(xany_work),
        "--nodata", "--autosave", "--no-auto-update-check",
    ]
    if classes_txt.exists():
        cmd += ["--labels", str(classes_txt), "--validatelabel", "exact"]

    try:
        proc = subprocess.Popen(cmd, env=_xany_env(exe))
        xany_pid = proc.pid
    except Exception as e:
        return {"ok": False, "error": str(e), "xany_pid": None}

    if not db.acquire_lock(db_path, session_id, xany_pid):
        return {"ok": False, "error": "Another X-AnyLabeling session is still running", "xany_pid": None}

    db.update_session(db_path, session_id, status="標記中", xany_pid=xany_pid)
    return {"ok": True, "error": None, "xany_pid": xany_pid}


def open_single_frame(db_path: Path, session_id: int, frame_idx: int) -> dict:
    """
    Launch X-AnyLabeling for a single frame only (correction mode).
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _db as db

    session = db.get_session_status(db_path, session_id)
    if not session:
        return {"ok": False, "error": "Session not found", "xany_pid": None}

    xany_project_dir = Path(session["xany_project_dir"])
    frames_dir = xany_project_dir / "frames"
    ann_dir = xany_project_dir / "annotations"

    frame_path = frames_dir / f"frame_{frame_idx:06d}.jpg"
    if not frame_path.exists():
        return {"ok": False, "error": f"Frame not found: {frame_path}", "xany_pid": None}

    single_ann_dir = xany_project_dir / "single_frame_correction"
    single_ann_dir.mkdir(parents=True, exist_ok=True)

    # Copy existing annotation for this frame into single_ann_dir
    src_ann = ann_dir / f"frame_{frame_idx:06d}.json"
    dst_ann = single_ann_dir / f"frame_{frame_idx:06d}.json"
    if src_ann.exists():
        dst_ann.write_bytes(src_ann.read_bytes())

    classes_txt = xany_project_dir / "classes.txt"
    exe = _get_xany_exe()
    cmd = _xany_command_prefix(exe) + [
        "--filename", str(frame_path),
        "--output", str(single_ann_dir),
        "--nodata", "--autosave", "--no-auto-update-check",
    ]
    if classes_txt.exists():
        cmd += ["--labels", str(classes_txt), "--validatelabel", "exact"]

    # Write metadata so update_after_single_close knows which frame to read
    (xany_project_dir / "single_frame_meta.json").write_text(
        json.dumps({"session_id": session_id, "frame_idx": frame_idx, "ann_dir": str(single_ann_dir)}),
        encoding="utf-8",
    )

    try:
        proc = subprocess.Popen(cmd, env=_xany_env(exe))
        xany_pid = proc.pid
    except Exception as e:
        return {"ok": False, "error": str(e), "xany_pid": None}

    if not db.acquire_lock(db_path, session_id, xany_pid):
        return {"ok": False, "error": "Another X-AnyLabeling session is still running", "xany_pid": None}

    db.update_session(db_path, session_id, xany_pid=xany_pid)
    return {"ok": True, "error": None, "xany_pid": xany_pid, "frame_idx": frame_idx}


def update_after_xany_close(db_path: Path, session_id: int) -> dict:
    """
    Scan xany_project_dir/annotations/, parse all JSON files, upsert frame_annotations,
    release lock, update summary, set status='已標記'.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _db as db

    session = db.get_session_status(db_path, session_id)
    if not session:
        return {"ok": False, "error": "Session not found"}

    xany_project_dir = Path(session["xany_project_dir"])
    ann_dir = xany_project_dir / "annotations"
    if not ann_dir.exists():
        return {"ok": False, "error": "Annotations directory not found"}

    upserted = 0
    for ann_file in sorted(ann_dir.glob("frame_*.json")):
        try:
            stem = ann_file.stem  # frame_000123
            frame_idx = int(stem.split("_")[1])
            ann_json = ann_file.read_text(encoding="utf-8")
            data = json.loads(ann_json)
            confs = []
            for shape in data.get("shapes", []):
                desc = shape.get("description", "")
                if desc.startswith("confidence="):
                    try:
                        confs.append(float(desc.split("=")[1]))
                    except ValueError:
                        pass
            conf_avg = sum(confs) / len(confs) if confs else None
            db.upsert_frame_annotation(db_path, session_id, frame_idx, ann_json, conf_avg, "xanylabeling")
            upserted += 1
        except Exception:
            pass

    summary = db.generate_summary(db_path, session_id)
    db.update_session(
        db_path, session_id,
        status="已標記",
        xany_pid=None,
        annotation_count=summary["frame_count"],
        last_summary=json.dumps(summary, ensure_ascii=False),
    )
    db.release_lock(db_path, session_id)

    return {"ok": True, "frames_upserted": upserted, "summary": summary}


def update_after_single_close(db_path: Path, session_id: int, frame_idx: int, single_ann_dir: Path) -> dict:
    """
    Parse the single-frame correction result and upsert only that frame.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _db as db

    ann_file = single_ann_dir / f"frame_{frame_idx:06d}.json"
    if not ann_file.exists():
        db.release_lock(db_path, session_id)
        return {"ok": False, "error": "Corrected annotation file not found"}

    ann_json = ann_file.read_text(encoding="utf-8")
    data = json.loads(ann_json)
    confs = []
    for shape in data.get("shapes", []):
        desc = shape.get("description", "")
        if desc.startswith("confidence="):
            try:
                confs.append(float(desc.split("=")[1]))
            except ValueError:
                pass
    conf_avg = sum(confs) / len(confs) if confs else 1.0
    db.upsert_frame_annotation(db_path, session_id, frame_idx, ann_json, conf_avg, "xanylabeling")

    # Also copy back to main annotations dir
    session = db.get_session_status(db_path, session_id)
    if session and session["xany_project_dir"]:
        main_ann = Path(session["xany_project_dir"]) / "annotations" / f"frame_{frame_idx:06d}.json"
        main_ann.parent.mkdir(parents=True, exist_ok=True)
        main_ann.write_text(ann_json, encoding="utf-8")

    summary = db.generate_summary(db_path, session_id)
    db.update_session(
        db_path, session_id,
        xany_pid=None,
        annotation_count=summary["frame_count"],
        last_summary=json.dumps(summary, ensure_ascii=False),
    )
    db.release_lock(db_path, session_id)

    return {"ok": True, "frame_idx": frame_idx, "summary": summary}


def sync_to_db(db_path: Path, session_ids: list[int]) -> dict:
    """
    Archive '已標記' sessions: move temp annotations to backup/, set status='已同步'.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _db as db
    import shutil

    synced: list[int] = []
    for sid in session_ids:
        session = db.get_session_status(db_path, sid)
        if not session or session["status"] not in ("已標記",):
            continue
        if session["xany_project_dir"]:
            xany_dir = Path(session["xany_project_dir"])
            backup_dir = xany_dir.parent / "backup" / xany_dir.name
            if xany_dir.exists():
                shutil.copytree(str(xany_dir), str(backup_dir), dirs_exist_ok=True)
        db.update_session(db_path, sid, status="已同步")
        synced.append(sid)

    return {"ok": True, "synced_session_ids": synced}


# ── PID monitoring ─────────────────────────────────────────────────────────────

_monitor_threads: dict[int, threading.Thread] = {}


def start_pid_monitor(db_path: Path, session_id: int, xany_pid: int, on_close_callback) -> None:
    """
    Start a background thread that polls psutil every 2s.
    When xany_pid dies, calls on_close_callback(session_id).
    """
    def _monitor():
        while True:
            time.sleep(2)
            if not psutil.pid_exists(xany_pid):
                on_close_callback(session_id)
                break

    t = threading.Thread(target=_monitor, daemon=True, name=f"xany-monitor-{session_id}")
    t.start()
    _monitor_threads[session_id] = t
