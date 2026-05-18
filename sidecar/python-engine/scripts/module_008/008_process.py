"""
module_008 process layer — no Streamlit imports.

Public API:
  start_propagation(session_dir, session_data) -> dict
  re_propagate(session_dir, from_frame_idx) -> dict
  save_correction(session_dir, frame_idx, bboxes) -> None
  export_xanylabeling(session_dir) -> dict
  get_task_status(session_dir) -> dict
  load_session(session_dir) -> dict | None
  load_annotation(session_dir, frame_idx) -> dict | None
  get_xany_exe(project_root) -> str
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


# ── helpers ───────────────────────────────────────────────────────────────────

def _session_path(session_dir: str | Path) -> Path:
    return Path(session_dir) / "session.json"


def _task_path(session_dir: str | Path) -> Path:
    return Path(session_dir) / "task.json"


def _ann_dir(session_dir: str | Path) -> Path:
    return Path(session_dir) / "annotations"


def _ann_path(session_dir: str | Path, frame_idx: int) -> Path:
    return _ann_dir(session_dir) / f"frame_{frame_idx:06d}.json"


def _worker_script() -> Path:
    return Path(__file__).resolve().parent / "_worker.py"


# ── public API ────────────────────────────────────────────────────────────────

def load_session(session_dir: str | Path) -> dict | None:
    p = _session_path(session_dir)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_annotation(session_dir: str | Path, frame_idx: int) -> dict | None:
    p = _ann_path(session_dir, frame_idx)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_task_status(session_dir: str | Path) -> dict:
    p = _task_path(session_dir)
    if not p.exists():
        return {"state": "idle", "progress": 0.0, "current_frame": 0, "total_frames": 0}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"state": "idle", "progress": 0.0, "current_frame": 0, "total_frames": 0}


def start_propagation(session_dir: str | Path, session_data: dict) -> dict:
    sd = Path(session_dir)
    sd.mkdir(parents=True, exist_ok=True)
    _session_path(sd).write_text(
        json.dumps(session_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Clear previous task.json so UI doesn't show stale done state
    tp = _task_path(sd)
    if tp.exists():
        tp.unlink()

    subprocess.Popen(
        [sys.executable, str(_worker_script()), str(sd)],
        cwd=str(Path(__file__).resolve().parent),
    )
    return {"state": "started", "session_dir": str(sd)}


def re_propagate(session_dir: str | Path, from_frame_idx: int) -> dict:
    sd = Path(session_dir)
    tp = _task_path(sd)
    if tp.exists():
        tp.unlink()
    subprocess.Popen(
        [sys.executable, str(_worker_script()), str(sd), "--from-frame", str(from_frame_idx)],
        cwd=str(Path(__file__).resolve().parent),
    )
    return {"state": "started", "from_frame": from_frame_idx}


def save_correction(
    session_dir: str | Path,
    frame_idx: int,
    bboxes: list[dict],
) -> None:
    """
    Overwrite a single frame's annotation with manually corrected bboxes.
    bboxes: list of {"label": str, "x1": float, "y1": float, "x2": float, "y2": float}
    """
    sd = Path(session_dir)
    session = load_session(sd) or {}
    img_w = session.get("width", 0)
    img_h = session.get("height", 0)

    shapes = []
    for b in bboxes:
        shapes.append({
            "label": b["label"],
            "shape_type": "rectangle",
            "points": [[float(b["x1"]), float(b["y1"])], [float(b["x2"]), float(b["y2"])]],
            "description": "confidence=1.000",
            "flags": {},
            "group_id": None,
            "other_data": {},
        })

    ann_dir = _ann_dir(sd)
    ann_dir.mkdir(parents=True, exist_ok=True)
    rel_path = f"../frames/frame_{frame_idx:06d}.jpg"
    data = {
        "version": "6.0.0",
        "imagePath": rel_path,
        "imageHeight": img_h,
        "imageWidth": img_w,
        "imageData": None,
        "flags": {},
        "shapes": shapes,
    }
    _ann_path(sd, frame_idx).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def export_xanylabeling(session_dir: str | Path) -> dict:
    sd = Path(session_dir)
    ann_dir = _ann_dir(sd)
    export_dir = sd / "exports" / "xanylabeling"
    export_dir.mkdir(parents=True, exist_ok=True)

    ann_files = sorted(ann_dir.glob("frame_*.json"))
    copied = []
    for f in ann_files:
        dest = export_dir / f.name
        shutil.copy2(f, dest)
        copied.append(f.name)

    # Also copy frames so the JSON imagePaths resolve
    frames_export = export_dir / "frames"
    frames_export.mkdir(exist_ok=True)
    frames_src = sd / "frames"
    for ann_name in copied:
        frame_name = ann_name.replace(".json", ".jpg")
        src = frames_src / frame_name
        if src.exists():
            shutil.copy2(src, frames_export / frame_name)

    manifest = {
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "session_dir": str(sd),
        "annotation_count": len(copied),
        "files": copied,
    }
    (export_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "export_dir": str(export_dir),
        "annotation_count": len(copied),
        "manifest": manifest,
    }


def get_xany_exe(project_root: str | Path) -> str:
    candidates = [
        Path(os.environ.get("XANYLABELING_EXE", "")),
        Path(project_root) / ".venv-xanylabeling" / "Scripts" / "xanylabeling.exe",
    ]
    for c in candidates:
        if str(c) and c.exists():
            return str(c)
    return "xanylabeling"


def xany_subprocess_env(executable: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONNOUSERSITE"] = "1"
    if executable:
        scripts_dir = str(Path(executable).resolve().parent)
        env["PATH"] = scripts_dir + os.pathsep + env.get("PATH", "")
    return env


def xany_command_prefix(executable: str) -> list[str]:
    exe = Path(executable)
    if exe.name.lower().startswith("xanylabeling"):
        python = exe.parent / "python.exe"
        if python.exists():
            return [str(python), "-m", "anylabeling.app"]
    return [str(exe)]


def list_annotated_frames(session_dir: str | Path) -> list[int]:
    ann_dir = _ann_dir(session_dir)
    if not ann_dir.exists():
        return []
    indices = []
    for p in sorted(ann_dir.glob("frame_*.json")):
        try:
            idx = int(p.stem.split("_")[1])
            indices.append(idx)
        except (IndexError, ValueError):
            pass
    return sorted(indices)


def execute_logic(params: dict) -> dict:
    """Required by cv_framework_runner. Starts propagation when anchor_bboxes are present."""
    if params.get("mode") != "tracking":
        return params

    anchor_bboxes = params.get("anchor_bboxes", [])
    if not anchor_bboxes:
        return {**params, "error": "請先在 X-AnyLabeling 畫好 bbox 後再執行。"}

    meta = params.get("meta", {})
    before_sec = float(params.get("before_sec", 1.0))
    after_sec = float(params.get("after_sec", 1.0))
    session_dir = Path(params["session_dir"])

    session_data = {
        "session_id": session_dir.name,
        "video_path": params["video_path"],
        "anchor_frame_idx": params["anchor_frame_idx"],
        "fps": meta.get("fps", 30.0),
        "width": meta.get("width", 0),
        "height": meta.get("height", 0),
        "time_range_sec": [-before_sec, after_sec],
        "labels": params.get("labels", []),
        "anchor_bboxes": anchor_bboxes,
        "state": "propagating",
    }
    start_propagation(session_dir, session_data)
    return params
