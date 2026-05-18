"""
Propagation subprocess worker for module_008.

Called by 008_process.py via subprocess.Popen:
    python _worker.py <session_dir> [--from-frame <idx>]

Reads session.json, propagates bboxes forward and backward across the time range,
writes per-frame X-AnyLabeling JSON to annotations/, and updates task.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import cv2
import numpy as np

# ── DINO availability ──────────────────────────────────────────────────────────

try:
    import torch
    from PIL import Image
    from transformers import AutoImageProcessor, AutoModel
    DINO_AVAILABLE = True
except ImportError:
    DINO_AVAILABLE = False

_DINO_MODEL_ID = "facebook/dinov2-small"
_DINO_INPUT_SIZE = 518
_DINO_PATCH_SIZE = 14
_DINO_N_PATCHES = _DINO_INPUT_SIZE // _DINO_PATCH_SIZE   # 37
_DINO_FEAT_DIM = 384

_dino_processor = None
_dino_model = None


def _ensure_dino():
    global _dino_processor, _dino_model
    if _dino_processor is None and DINO_AVAILABLE:
        _dino_processor = AutoImageProcessor.from_pretrained(_DINO_MODEL_ID)
        _dino_model = AutoModel.from_pretrained(_DINO_MODEL_ID)
        _dino_model.eval()


def _extract_features(frame_bgr: np.ndarray) -> np.ndarray | None:
    if not DINO_AVAILABLE:
        return None
    _ensure_dino()
    pil = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    pil = pil.resize((_DINO_INPUT_SIZE, _DINO_INPUT_SIZE), Image.LANCZOS)
    inputs = _dino_processor(
        images=pil,
        return_tensors="pt",
        do_resize=False,
        do_center_crop=False,
    )
    with torch.no_grad():
        out = _dino_model(**inputs)
    tokens = out.last_hidden_state[0, 1:, :].cpu().numpy()
    grid = int(tokens.shape[0] ** 0.5)
    features = tokens.reshape(grid, grid, -1).astype(np.float32)
    norms = np.linalg.norm(features, axis=-1, keepdims=True)
    features /= norms + 1e-8
    return features


# ── Optical flow tracking ──────────────────────────────────────────────────────

def _optical_flow_track(
    src_frame: np.ndarray,
    bbox: tuple,
    tgt_frame: np.ndarray,
    img_w: int,
    img_h: int,
) -> tuple[tuple, float]:
    x1, y1, x2, y2 = bbox
    w, h = x2 - x1, y2 - y1

    ix1 = x1 + w * 0.25
    iy1 = y1 + h * 0.25
    ix2 = x2 - w * 0.25
    iy2 = y2 - h * 0.25
    icx = (ix1 + ix2) / 2
    icy = (iy1 + iy2) / 2

    pts = np.array([
        [ix1, iy1], [icx, iy1], [ix2, iy1],
        [ix1, icy], [icx, icy], [ix2, icy],
        [ix1, iy2], [icx, iy2], [ix2, iy2],
    ], dtype=np.float32).reshape(-1, 1, 2)

    src_gray = cv2.cvtColor(src_frame, cv2.COLOR_BGR2GRAY)
    tgt_gray = cv2.cvtColor(tgt_frame, cv2.COLOR_BGR2GRAY)

    new_pts, status, _ = cv2.calcOpticalFlowPyrLK(
        src_gray, tgt_gray, pts, None,
        winSize=(31, 31),
        maxLevel=3,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
    )

    good_mask = status.ravel() == 1
    if good_mask.sum() < 3:
        return bbox, 0.1

    good_old = pts[good_mask].reshape(-1, 2)
    good_new = new_pts[good_mask].reshape(-1, 2)
    dx = float(np.median(good_new[:, 0] - good_old[:, 0]))
    dy = float(np.median(good_new[:, 1] - good_old[:, 1]))

    nx1 = float(np.clip(x1 + dx, 0, img_w))
    ny1 = float(np.clip(y1 + dy, 0, img_h))
    nx2 = float(np.clip(x2 + dx, 0, img_w))
    ny2 = float(np.clip(y2 + dy, 0, img_h))

    return (nx1, ny1, nx2, ny2), float(good_mask.mean())


# ── DINO center-patch similarity ───────────────────────────────────────────────

def _center_patch_similarity(
    src_feat: np.ndarray,
    src_bbox: tuple,
    tgt_feat: np.ndarray,
    tgt_bbox: tuple,
    img_w: int,
    img_h: int,
) -> float:
    def center_vec(feat, bbox):
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2 * _DINO_INPUT_SIZE / img_w
        cy = (y1 + y2) / 2 * _DINO_INPUT_SIZE / img_h
        px = int(np.clip(cx / _DINO_PATCH_SIZE, 0, _DINO_N_PATCHES - 1))
        py = int(np.clip(cy / _DINO_PATCH_SIZE, 0, _DINO_N_PATCHES - 1))
        return feat[py, px]

    va = center_vec(src_feat, src_bbox)
    vb = center_vec(tgt_feat, tgt_bbox)
    return float(np.clip(np.dot(va, vb), 0.0, 1.0))


# ── X-AnyLabeling JSON helpers ─────────────────────────────────────────────────

def _bbox_to_xany_shape(label: str, bbox: tuple, confidence: float) -> dict:
    x1, y1, x2, y2 = bbox
    return {
        "label": label,
        "shape_type": "rectangle",
        "points": [[float(x1), float(y1)], [float(x2), float(y2)]],
        "description": f"confidence={confidence:.3f}",
        "flags": {},
        "group_id": None,
        "other_data": {},
    }


def _write_annotation(
    ann_dir: Path,
    frame_idx: int,
    frame_path: Path,
    shapes: list[dict],
    img_w: int,
    img_h: int,
) -> None:
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
    p = ann_dir / f"frame_{frame_idx:06d}.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_annotation(ann_dir: Path, frame_idx: int) -> list[dict]:
    p = ann_dir / f"frame_{frame_idx:06d}.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("shapes", [])
    except Exception:
        return []


def _shapes_to_bboxes(shapes: list[dict]) -> list[dict]:
    result = []
    for s in shapes:
        if s.get("shape_type") != "rectangle":
            continue
        pts = s.get("points", [])
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        if not xs or not ys:
            continue
        result.append({
            "label": s.get("label", ""),
            "bbox": (min(xs), min(ys), max(xs), max(ys)),
            "confidence": 1.0,
        })
    return result


# ── Task JSON helpers ──────────────────────────────────────────────────────────

def _write_task(session_dir: Path, state: str, progress: float, current: int, total: int, error: str | None = None):
    data = {
        "state": state,
        "progress": progress,
        "current_frame": current,
        "total_frames": total,
        "dino_available": DINO_AVAILABLE,
        "error": error,
    }
    (session_dir / "task.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── Frame extraction ───────────────────────────────────────────────────────────

def _extract_frame(cap: cv2.VideoCapture, frame_idx: int, frames_dir: Path) -> np.ndarray | None:
    dest = frames_dir / f"frame_{frame_idx:06d}.jpg"
    if dest.exists():
        return cv2.imread(str(dest))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    if not ret:
        return None
    cv2.imwrite(str(dest), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return frame


# ── Single propagation step ────────────────────────────────────────────────────

def _propagate_step(
    cap: cv2.VideoCapture,
    src_bboxes: list[dict],
    src_frame_idx: int,
    tgt_frame_idx: int,
    frames_dir: Path,
    features_dir: Path,
    img_w: int,
    img_h: int,
) -> list[dict]:
    src_frame = _extract_frame(cap, src_frame_idx, frames_dir)
    tgt_frame = _extract_frame(cap, tgt_frame_idx, frames_dir)
    if src_frame is None or tgt_frame is None:
        return src_bboxes

    src_feat = None
    tgt_feat = None
    if DINO_AVAILABLE:
        src_npy = features_dir / f"frame_{src_frame_idx:06d}.npy"
        tgt_npy = features_dir / f"frame_{tgt_frame_idx:06d}.npy"
        if not src_npy.exists():
            feat = _extract_features(src_frame)
            if feat is not None:
                np.save(str(src_npy), feat)
            src_feat = feat
        else:
            src_feat = np.load(str(src_npy))
        if not tgt_npy.exists():
            feat = _extract_features(tgt_frame)
            if feat is not None:
                np.save(str(tgt_npy), feat)
            tgt_feat = feat
        else:
            tgt_feat = np.load(str(tgt_npy))

    result = []
    for box in src_bboxes:
        label = box["label"]
        src_bbox = box["bbox"]

        new_bbox, of_conf = _optical_flow_track(src_frame, src_bbox, tgt_frame, img_w, img_h)

        if src_feat is not None and tgt_feat is not None:
            dino_conf = _center_patch_similarity(src_feat, src_bbox, tgt_feat, new_bbox, img_w, img_h)
            conf = of_conf * 0.5 + dino_conf * 0.5
        else:
            conf = of_conf

        result.append({"label": label, "bbox": new_bbox, "confidence": conf})

    return result


# ── Main worker ────────────────────────────────────────────────────────────────

def run(session_dir: Path, from_frame_idx: int | None = None):
    session_file = session_dir / "session.json"
    if not session_file.exists():
        sys.exit(f"session.json not found in {session_dir}")

    session = json.loads(session_file.read_text(encoding="utf-8"))
    video_path = session["video_path"]
    anchor_idx = session["anchor_frame_idx"]
    time_range = session.get("time_range_sec", [-1.0, 1.0])

    frames_dir = session_dir / "frames"
    features_dir = session_dir / "features"
    ann_dir = session_dir / "annotations"
    for d in (frames_dir, features_dir, ann_dir):
        d.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        _write_task(session_dir, "error", 0.0, 0, 0, f"Cannot open video: {video_path}")
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames_video = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    img_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    img_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    before_sec = abs(time_range[0]) if time_range[0] < 0 else time_range[0]
    after_sec = time_range[1]

    start_idx = max(0, anchor_idx - int(before_sec * fps))
    end_idx = min(total_frames_video - 1, anchor_idx + int(after_sec * fps))
    total_steps = (anchor_idx - start_idx) + (end_idx - anchor_idx)

    propagate_from = from_frame_idx if from_frame_idx is not None else anchor_idx

    # Load anchor / correction bboxes
    anchor_shapes = _read_annotation(ann_dir, anchor_idx)
    if not anchor_shapes:
        # Fall back to session anchor_bboxes (from X-AnyLabeling initial draw)
        raw = session.get("anchor_bboxes", [])
        anchor_shapes = [
            _bbox_to_xany_shape(b["label"], (b["x1"], b["y1"], b["x2"], b["y2"]), 1.0)
            for b in raw
        ]
        # Write anchor annotation file
        _write_annotation(ann_dir, anchor_idx, frames_dir / f"frame_{anchor_idx:06d}.jpg",
                          anchor_shapes, img_w, img_h)

    current_bboxes = _shapes_to_bboxes(anchor_shapes)

    if not current_bboxes:
        _write_task(session_dir, "error", 0.0, 0, 0, "No anchor bboxes found")
        cap.release()
        sys.exit(1)

    # If re-propagating from a correction frame, load that frame's bboxes
    if propagate_from != anchor_idx:
        correction_shapes = _read_annotation(ann_dir, propagate_from)
        if correction_shapes:
            current_bboxes = _shapes_to_bboxes(correction_shapes)
        start_idx = max(0, propagate_from - int(before_sec * fps))
        end_idx = min(total_frames_video - 1, propagate_from + int(after_sec * fps))
        total_steps = (propagate_from - start_idx) + (end_idx - propagate_from)

    _write_task(session_dir, "running", 0.0, 0, total_steps)
    done = 0

    # Backward pass (from anchor/correction toward start)
    prev_bboxes = current_bboxes
    for idx in range(propagate_from - 1, start_idx - 1, -1):
        new_bboxes = _propagate_step(cap, prev_bboxes, idx + 1, idx,
                                     frames_dir, features_dir, img_w, img_h)
        shapes = [_bbox_to_xany_shape(b["label"], b["bbox"], b["confidence"]) for b in new_bboxes]
        _write_annotation(ann_dir, idx, frames_dir / f"frame_{idx:06d}.jpg", shapes, img_w, img_h)
        prev_bboxes = new_bboxes
        done += 1
        _write_task(session_dir, "running", done / max(total_steps, 1), done, total_steps)

    # Forward pass (from anchor/correction toward end)
    prev_bboxes = current_bboxes
    for idx in range(propagate_from + 1, end_idx + 1):
        new_bboxes = _propagate_step(cap, prev_bboxes, idx - 1, idx,
                                     frames_dir, features_dir, img_w, img_h)
        shapes = [_bbox_to_xany_shape(b["label"], b["bbox"], b["confidence"]) for b in new_bboxes]
        _write_annotation(ann_dir, idx, frames_dir / f"frame_{idx:06d}.jpg", shapes, img_w, img_h)
        prev_bboxes = new_bboxes
        done += 1
        _write_task(session_dir, "running", done / max(total_steps, 1), done, total_steps)

    # Write anchor frame itself (confidence=1.0, is anchor)
    anchor_shapes_final = [_bbox_to_xany_shape(b["label"], b["bbox"], 1.0) for b in current_bboxes]
    _write_annotation(ann_dir, propagate_from,
                      frames_dir / f"frame_{propagate_from:06d}.jpg",
                      anchor_shapes_final, img_w, img_h)

    cap.release()
    _write_task(session_dir, "done", 1.0, total_steps, total_steps)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("session_dir")
    parser.add_argument("--from-frame", type=int, default=None)
    args = parser.parse_args()

    try:
        run(Path(args.session_dir), args.from_frame)
    except Exception:
        sd = Path(args.session_dir)
        _write_task(sd, "error", 0.0, 0, 0, traceback.format_exc())
        raise
