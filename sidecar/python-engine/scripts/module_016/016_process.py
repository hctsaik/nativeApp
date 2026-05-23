from __future__ import annotations

"""
016_process.py — AI Pre-labeling 核心邏輯（無 Streamlit import）

YOLO 模式：
  - 使用 ultralytics（YOLOv5/v8/v11）做 object detection
  - 每張圖輸出同名 .json（X-AnyLabeling rectangle shapes）

Classifier 模式：
  - 使用 torchvision 或 timm 載入分類模型
  - 輸出整張圖的 label 到 X-AnyLabeling flags 欄位
  - 同時更新 module_012_classifications_{manifest_key}.json

跳過：已存在 .json 且 overwrite_existing=False 的圖片。
"""

import importlib.util as _ilu
import json
import os
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_016_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_mdb_spec = _ilu.spec_from_file_location(
    "_manifest_db", _HERE.parent / "shared" / "_manifest_db.py"
)
_mdb = _ilu.module_from_spec(_mdb_spec)
_mdb_spec.loader.exec_module(_mdb)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CIM_LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", str(_PROJECT_ROOT / "tmp" / "cim_log")))


# ─── X-AnyLabeling JSON helpers ───────────────────────────────────────────────

def _xany_rect(label: str, x1: float, y1: float, x2: float, y2: float,
               score: float | None = None) -> dict:
    return {
        "label": label,
        "score": round(score, 4) if score is not None else None,
        "points": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
        "group_id": None,
        "description": "",
        "difficult": False,
        "shape_type": "rectangle",
        "flags": {},
    }


def _write_xany_json(file_path: str, shapes: list[dict],
                     img_w: int, img_h: int, flags: dict | None = None) -> None:
    ann_path = Path(file_path).with_suffix(".json")
    data = {
        "version": "1.0.0",
        "flags": flags or {},
        "shapes": shapes,
        "imagePath": Path(file_path).name,
        "imageData": None,
        "imageHeight": img_h,
        "imageWidth": img_w,
    }
    ann_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_image_size(file_path: str) -> tuple[int, int]:
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            return img.width, img.height
    except Exception:
        return 0, 0


# ─── YOLO 推論 ────────────────────────────────────────────────────────────────

def _run_yolo(items: list[dict], model_path: str,
              conf: float, overwrite: bool,
              progress_cb=None) -> dict:
    try:
        from ultralytics import YOLO
    except ImportError:
        return {"ok": 0, "skipped": 0, "errors": 0,
                "error_detail": "ultralytics 未安裝，請執行：pip install ultralytics"}

    model = YOLO(model_path)
    ok = skipped = errors = 0
    item_results: list[dict] = []

    for it in items:
        fp = it.get("file_path", "")
        if not fp or not Path(fp).exists():
            errors += 1
            item_results.append({"file": fp, "status": "error", "detail": "檔案不存在"})
            continue

        ann_path = Path(fp).with_suffix(".json")
        if ann_path.exists() and not overwrite:
            skipped += 1
            item_results.append({"file": Path(fp).name, "status": "skipped", "detail": "已有標注"})
            continue

        try:
            results = model(fp, conf=conf, verbose=False)
            r = results[0]
            img_w, img_h = int(r.orig_shape[1]), int(r.orig_shape[0])
            shapes: list[dict] = []
            for box in r.boxes:
                x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
                cls_id = int(box.cls[0])
                label = model.names.get(cls_id, str(cls_id))
                score = float(box.conf[0])
                shapes.append(_xany_rect(label, x1, y1, x2, y2, score))

            _write_xany_json(fp, shapes, img_w, img_h)
            ok += 1
            item_results.append({
                "file": Path(fp).name,
                "status": "ok",
                "detail": f"{len(shapes)} 個 bbox",
            })
        except Exception as exc:
            errors += 1
            item_results.append({"file": Path(fp).name, "status": "error", "detail": str(exc)})

        if progress_cb:
            progress_cb(ok + skipped + errors, Path(fp).name, ok, skipped, errors)

    return {"ok": ok, "skipped": skipped, "errors": errors, "item_results": item_results}


# ─── Classifier 推論 ──────────────────────────────────────────────────────────

def _run_classifier(items: list[dict], model_path: str,
                    conf: float, overwrite: bool,
                    manifest_id: str, progress_cb=None) -> dict:
    """
    torchvision / timm 分類模型推論。
    模型需為標準 state_dict（含 class_names 或 labels 屬性），或附帶同名 .json 標籤檔。
    """
    try:
        import torch
        import torchvision.transforms as T
        from PIL import Image as PilImage
    except ImportError:
        return {"ok": 0, "skipped": 0, "errors": 0,
                "error_detail": "torch / torchvision 未安裝"}

    # 嘗試讀取 class labels（同名 .json 或 .txt）
    model_p = Path(model_path)
    labels: list[str] = []
    for ext in (".json", ".txt"):
        lbl_file = model_p.with_suffix(ext)
        if lbl_file.exists():
            try:
                content = lbl_file.read_text(encoding="utf-8")
                if ext == ".json":
                    data = json.loads(content)
                    if isinstance(data, list):
                        labels = data
                    elif isinstance(data, dict):
                        labels = [data[str(i)] for i in range(len(data))]
                else:
                    labels = [ln.strip() for ln in content.splitlines() if ln.strip()]
            except Exception:
                pass
            break

    try:
        checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)
        if isinstance(checkpoint, dict) and "model" in checkpoint:
            state = checkpoint["model"].state_dict() if hasattr(checkpoint["model"], "state_dict") else checkpoint["model"]
            if not labels and "class_names" in checkpoint:
                labels = checkpoint["class_names"]
        elif hasattr(checkpoint, "state_dict"):
            state = checkpoint.state_dict()
        else:
            state = checkpoint

        # 嘗試從 state dict 推斷 num_classes
        last_key = [k for k in state if "weight" in k]
        num_classes = state[last_key[-1]].shape[0] if last_key else (len(labels) or 2)

        import torchvision.models as tvm
        model = tvm.resnet50(weights=None)
        model.fc = torch.nn.Linear(model.fc.in_features, num_classes)
        model.load_state_dict(state, strict=False)
        model.eval()
    except Exception as exc:
        return {"ok": 0, "skipped": 0, "errors": 0,
                "error_detail": f"模型載入失敗：{exc}"}

    transform = T.Compose([
        T.Resize(256), T.CenterCrop(224), T.ToTensor(),
        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    ok = skipped = errors = 0
    item_results: list[dict] = []
    classifications: dict[str, str] = {}

    # 讀取已有的分類結果
    clf_path = _CIM_LOG_DIR / "config" / f"module_012_classifications_{manifest_id[:12]}.json"
    if clf_path.exists():
        try:
            classifications = json.loads(clf_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    for it in items:
        fp = it.get("file_path", "")
        item_id = it.get("item_id", "")
        if not fp or not Path(fp).exists():
            errors += 1
            item_results.append({"file": fp, "status": "error", "detail": "檔案不存在"})
            continue

        ann_path = Path(fp).with_suffix(".json")
        if ann_path.exists() and not overwrite:
            skipped += 1
            item_results.append({"file": Path(fp).name, "status": "skipped", "detail": "已有標注"})
            continue

        try:
            with PilImage.open(fp).convert("RGB") as img:
                img_w, img_h = img.width, img.height
                tensor = transform(img).unsqueeze(0)

            with torch.no_grad():
                logits = model(tensor)
                probs = torch.softmax(logits, dim=1)[0]
                top_conf, top_idx = probs.max(0)

            top_conf_val = float(top_conf)
            top_idx_val = int(top_idx)
            label = labels[top_idx_val] if labels and top_idx_val < len(labels) else str(top_idx_val)

            if top_conf_val >= conf:
                _write_xany_json(fp, [], img_w, img_h,
                                  flags={"classification": label, "confidence": round(top_conf_val, 4)})
                classifications[item_id] = label
                ok += 1
                item_results.append({
                    "file": Path(fp).name, "status": "ok",
                    "detail": f"{label} ({top_conf_val:.2%})",
                })
            else:
                skipped += 1
                item_results.append({
                    "file": Path(fp).name, "status": "low_conf",
                    "detail": f"{label} ({top_conf_val:.2%}) < threshold",
                })
        except Exception as exc:
            errors += 1
            item_results.append({"file": Path(fp).name, "status": "error", "detail": str(exc)})

        if progress_cb:
            progress_cb(ok + skipped + errors, Path(fp).name, ok, skipped, errors)

    # 寫回分類結果
    if classifications:
        clf_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = clf_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(classifications, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, clf_path)

    return {"ok": ok, "skipped": skipped, "errors": errors, "item_results": item_results}


# ─── 主流程 ───────────────────────────────────────────────────────────────────

def execute_logic(params: dict) -> dict:
    manifest_id: str = params.get("manifest_id", "")
    model_type: str = params.get("model_type", "yolo")
    model_path: str = params.get("model_path", "")
    conf: float = float(params.get("conf_threshold", 0.25))
    overwrite: bool = bool(params.get("overwrite_existing", False))

    _base = {
        "manifest_id": manifest_id,
        "model_type": model_type,
        "model_path": model_path,
        "ok": 0, "skipped": 0, "errors": 0,
        "item_results": [],
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }

    if not manifest_id:
        return {**_base, "mode": "error", "error": "未選擇 Manifest"}

    if not model_path:
        return {**_base, "mode": "error", "error": "未選擇模型檔案"}

    if not Path(model_path).exists():
        return {**_base, "mode": "error", "error": f"模型檔案不存在：{model_path}"}

    db_path = _cfg.get_manifest_db_path()
    manifest = _mdb.get_manifest(db_path, manifest_id)
    if manifest is None:
        return {**_base, "mode": "error", "error": f"找不到 Manifest：{manifest_id}"}

    items = _mdb.get_manifest_items(db_path, manifest_id)
    total = len(items)
    _base["total_items"] = total

    started_at = _base["started_at"]

    def _progress_cb(done: int, current: str, ok: int, skipped: int, errors: int) -> None:
        _cfg.write_progress(done, total, current, ok, skipped, errors,
                            started_at, running=True)

    _cfg.write_progress(0, total, "", 0, 0, 0, started_at, running=True)

    if model_type == "yolo":
        stats = _run_yolo(items, model_path, conf, overwrite, progress_cb=_progress_cb)
    else:
        stats = _run_classifier(items, model_path, conf, overwrite, manifest_id,
                                progress_cb=_progress_cb)

    if "error_detail" in stats:
        _cfg.write_progress(0, total, "", 0, 0, 0, started_at, running=False)
        return {**_base, "mode": "error", "error": stats["error_detail"]}

    _cfg.write_progress(
        stats["ok"] + stats["skipped"] + stats["errors"], total, "",
        stats["ok"], stats["skipped"], stats["errors"],
        started_at, running=False,
    )
    return {
        **_base,
        "mode": "done",
        "error": None,
        "ok": stats["ok"],
        "skipped": stats["skipped"],
        "errors": stats["errors"],
        "item_results": stats.get("item_results", []),
    }
