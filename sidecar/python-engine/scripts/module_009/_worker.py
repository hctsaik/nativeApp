"""
Tracking background worker for module_009.

Called by _xany_launcher.py via subprocess.Popen:
    python _worker.py <db_path> <session_id>

Reads asset + anchor_bboxes from annotation_sessions/video_assets,
runs DINOv2+LK tracking, writes per-frame JSON, and INSERTs into frame_annotations.
On completion sets status='標記中' so the launcher can open X-AnyLabeling.
"""
from __future__ import annotations

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
_DINO_N_PATCHES = _DINO_INPUT_SIZE // _DINO_PATCH_SIZE
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
        images=pil, return_tensors="pt", do_resize=False, do_center_crop=False
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
        winSize=(31, 31), maxLevel=3,
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


def _center_patch_similarity(
    src_feat: np.ndarray, src_bbox: tuple,
    tgt_feat: np.ndarray, tgt_bbox: tuple,
    img_w: int, img_h: int,
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


# ── Frame / annotation helpers ─────────────────────────────────────────────────

def _extract_frame(cap: cv2.VideoCapture, frame_idx: int, frames_dir: Path) -> np.ndarray | None:
    dest = frames_dir / f"frame_{frame_idx:06d}.jpg"
    if dest.exists():
        return cv2.imread(str(dest))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    if not ret:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dest), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return frame


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


def _build_xany_json(
    shapes: list[dict], frame_idx: int, img_w: int, img_h: int
) -> dict:
    return {
        "version": "6.0.0",
        "imagePath": f"../frames/frame_{frame_idx:06d}.jpg",
        "imageHeight": img_h,
        "imageWidth": img_w,
        "imageData": None,
        "flags": {},
        "shapes": shapes,
    }


def _extract_confidence(shapes: list[dict]) -> float:
    confs = []
    for s in shapes:
        desc = s.get("description", "")
        if desc.startswith("confidence="):
            try:
                confs.append(float(desc.split("=")[1]))
            except ValueError:
                pass
    return sum(confs) / len(confs) if confs else 0.0


def _propagate_step(
    cap, src_bboxes, src_idx, tgt_idx,
    frames_dir, features_dir, img_w, img_h,
) -> list[dict]:
    src_frame = _extract_frame(cap, src_idx, frames_dir)
    tgt_frame = _extract_frame(cap, tgt_idx, frames_dir)
    if src_frame is None or tgt_frame is None:
        return src_bboxes

    src_feat = tgt_feat = None
    if DINO_AVAILABLE:
        src_npy = features_dir / f"frame_{src_idx:06d}.npy"
        tgt_npy = features_dir / f"frame_{tgt_idx:06d}.npy"
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


# ── Main ───────────────────────────────────────────────────────────────────────

def run(db_path: Path, session_id: int) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _db as db

    session = db.get_session_status(db_path, session_id)
    if not session:
        sys.exit(f"Session {session_id} not found")

    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    asset = conn.execute(
        "SELECT * FROM video_assets WHERE id=?", (session["asset_id"],)
    ).fetchone()
    conn.close()

    if asset is None:
        db.update_session(db_path, session_id, status="未標記")
        sys.exit("Asset not found")

    xany_project_dir = Path(session["xany_project_dir"])
    frames_dir = xany_project_dir / "frames"
    features_dir = xany_project_dir / "features"
    ann_dir = xany_project_dir / "annotations"
    for d in (frames_dir, features_dir, ann_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Load anchor info written by start_annotation()
    anchor_file = xany_project_dir / "anchor_info.json"
    if not anchor_file.exists():
        db.update_session(db_path, session_id, status="未標記")
        sys.exit("anchor_info.json not found")

    anchor_info = json.loads(anchor_file.read_text(encoding="utf-8"))
    video_path = asset["file_path"]
    anchor_idx = anchor_info["anchor_frame_idx"]
    before_sec = float(anchor_info.get("before_sec", 1.0))
    after_sec = float(anchor_info.get("after_sec", 1.0))
    raw_bboxes = anchor_info.get("anchor_bboxes", [])

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        db.update_session(db_path, session_id, status="未標記")
        sys.exit(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames_video = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    img_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    img_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    start_idx = max(0, anchor_idx - int(before_sec * fps))
    end_idx = min(total_frames_video - 1, anchor_idx + int(after_sec * fps))

    anchor_bboxes = [
        {"label": b["label"], "bbox": (b["x1"], b["y1"], b["x2"], b["y2"]), "confidence": 1.0}
        for b in raw_bboxes
    ]

    def write_frame(frame_idx: int, bboxes: list[dict]) -> None:
        shapes = [_bbox_to_xany_shape(b["label"], b["bbox"], b["confidence"]) for b in bboxes]
        ann_data = _build_xany_json(shapes, frame_idx, img_w, img_h)
        ann_json = json.dumps(ann_data, ensure_ascii=False, indent=2)
        (ann_dir / f"frame_{frame_idx:06d}.json").write_text(ann_json, encoding="utf-8")
        conf_avg = _extract_confidence(shapes)
        db.upsert_frame_annotation(db_path, session_id, frame_idx, ann_json, conf_avg, "tracking")

    # Write anchor frame itself
    _extract_frame(cap, anchor_idx, frames_dir)
    write_frame(anchor_idx, anchor_bboxes)

    # Backward pass
    prev = anchor_bboxes
    for idx in range(anchor_idx - 1, start_idx - 1, -1):
        new_bboxes = _propagate_step(cap, prev, idx + 1, idx, frames_dir, features_dir, img_w, img_h)
        _extract_frame(cap, idx, frames_dir)
        write_frame(idx, new_bboxes)
        prev = new_bboxes

    # Forward pass
    prev = anchor_bboxes
    for idx in range(anchor_idx + 1, end_idx + 1):
        new_bboxes = _propagate_step(cap, prev, idx - 1, idx, frames_dir, features_dir, img_w, img_h)
        _extract_frame(cap, idx, frames_dir)
        write_frame(idx, new_bboxes)
        prev = new_bboxes

    cap.release()
    db.update_session(db_path, session_id, status="標記中", tracking_job_pid=None)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python _worker.py <db_path> <session_id>", file=sys.stderr)
        sys.exit(1)

    db_path_arg = Path(sys.argv[1])
    session_id_arg = int(sys.argv[2])
    try:
        run(db_path_arg, session_id_arg)
    except Exception:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        try:
            import _db as db
            db.update_session(db_path_arg, session_id_arg, status="未標記")
        except Exception:
            pass
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(1)
