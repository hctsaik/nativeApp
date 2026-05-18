from __future__ import annotations

"""
011_process.py — Module 011 Result Sink 核心邏輯
無 Streamlit import。
"""

import csv
import importlib.util as _ilu
import json
import os
import random
import shutil
import uuid
from pathlib import Path

# ─── 動態載入 _manifest_db ────────────────────────────────────────────────────

_HERE = Path(__file__).resolve().parent
_spec = _ilu.spec_from_file_location(
    "_manifest_db", _HERE.parent / "shared" / "_manifest_db.py"
)
_mdb = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mdb)  # type: ignore[union-attr]

# ─── 路徑慣例 ─────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parents[4]  # nativeApp
_CIM_LOG_DIR = Path(
    os.environ.get("CIM_LOG_DIR", str(_PROJECT_ROOT / "tmp" / "cim_log"))
)


# ─── 輔助函式 ─────────────────────────────────────────────────────────────────


def _parse_bbox_from_shapes(shapes: list[dict]) -> list[dict]:
    """
    從 xanylabeling-style shapes 解析出 bbox list。

    shapes[i] = {
        "label": str,
        "points": [[x1,y1],[x2,y1],[x2,y2],[x1,y2]],
        "shape_type": "rectangle"
    }
    回傳: [{"label": str, "x1": float, "y1": float, "x2": float, "y2": float}]
    """
    results: list[dict] = []
    for shape in shapes:
        label = shape.get("label", "")
        points = shape.get("points", [])
        shape_type = shape.get("shape_type", "")

        if shape_type != "rectangle" or len(points) < 2:
            continue

        xs = [p[0] for p in points if len(p) >= 2]
        ys = [p[1] for p in points if len(p) >= 2]

        if not xs or not ys:
            continue

        results.append(
            {
                "label": label,
                "x1": float(min(xs)),
                "y1": float(min(ys)),
                "x2": float(max(xs)),
                "y2": float(max(ys)),
            }
        )
    return results


def stratified_split(
    item_ids: list[str],
    item_labels: dict[str, str],
    ratios: dict,
) -> dict[str, list[str]]:
    """
    依 ratios {"train": 0.7, "val": 0.15, "test": 0.15} 分割。

    item_labels: {item_id: label}（主要標籤）
    若某類別樣本不足（< 3），使用隨機切割。
    回傳: {"train": [...], "val": [...], "test": [...]}
    """
    if not item_ids:
        return {"train": [], "val": [], "test": []}

    train_r = ratios.get("train", 0.7)
    val_r = ratios.get("val", 0.15)
    # test_r 由 1 - train_r - val_r 決定，不直接使用

    # 依標籤分組
    label_groups: dict[str, list[str]] = {}
    for iid in item_ids:
        lbl = item_labels.get(iid, "__unknown__")
        label_groups.setdefault(lbl, []).append(iid)

    train_ids: list[str] = []
    val_ids: list[str] = []
    test_ids: list[str] = []

    for lbl, ids in label_groups.items():
        shuffled = ids[:]
        random.shuffle(shuffled)

        n = len(shuffled)
        if n < 3:
            # 樣本不足，全部放 train
            train_ids.extend(shuffled)
            continue

        n_train = max(1, round(n * train_r))
        n_val = max(0, round(n * val_r))
        # 確保 n_train + n_val <= n - 1（至少留一個給 test）
        if n_train + n_val >= n:
            n_val = max(0, n - n_train - 1)

        train_ids.extend(shuffled[:n_train])
        val_ids.extend(shuffled[n_train : n_train + n_val])
        test_ids.extend(shuffled[n_train + n_val :])

    return {"train": train_ids, "val": val_ids, "test": test_ids}


def _random_split(
    item_ids: list[str],
    ratios: dict,
) -> dict[str, list[str]]:
    """隨機切割（非 stratified）。"""
    shuffled = item_ids[:]
    random.shuffle(shuffled)
    n = len(shuffled)
    if n == 0:
        return {"train": [], "val": [], "test": []}

    train_r = ratios.get("train", 0.7)
    val_r = ratios.get("val", 0.15)

    n_train = max(0, round(n * train_r))
    n_val = max(0, round(n * val_r))
    if n_train + n_val > n:
        n_val = n - n_train

    return {
        "train": shuffled[:n_train],
        "val": shuffled[n_train : n_train + n_val],
        "test": shuffled[n_train + n_val :],
    }


# ─── 匯出函式 ─────────────────────────────────────────────────────────────────


def export_coco_json(
    items: list[dict],
    results: list[dict],
    split_groups: dict[str, list[str]],
    output_dir: Path,
) -> dict[str, str]:
    """
    輸出三個 COCO JSON 檔：train.json, val.json, test.json。
    COCO annotation bbox 格式：[x, y, width, height]（左上角 + 寬高）。
    回傳 {"train": "path/train.json", "val": ..., "test": ...}
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # 建立 item_id → item 對照表
    item_map: dict[str, dict] = {it["item_id"]: it for it in items}

    # 建立 item_id → result 對照表
    result_map: dict[str, dict] = {r["item_id"]: r for r in results}

    # 蒐集所有類別
    all_labels: set[str] = set()
    for r in results:
        ann_str = r.get("annotation_json", "{}")
        try:
            ann = json.loads(ann_str)
        except Exception:
            ann = {}
        for shape in ann.get("shapes", []):
            lbl = shape.get("label", "")
            if lbl:
                all_labels.add(lbl)
        # 也從 label 欄位收集
        if r.get("label"):
            all_labels.add(r["label"])

    # 若完全沒有標籤，至少放一個佔位
    sorted_labels = sorted(all_labels)
    categories = [
        {"id": idx + 1, "name": lbl, "supercategory": "none"}
        for idx, lbl in enumerate(sorted_labels)
    ]
    label_to_cat_id = {lbl: idx + 1 for idx, lbl in enumerate(sorted_labels)}

    export_paths: dict[str, str] = {}

    for split_name, split_ids in split_groups.items():
        images = []
        annotations = []
        ann_id = 1

        for img_id, item_id in enumerate(split_ids, start=1):
            it = item_map.get(item_id)
            if it is None:
                continue

            file_path = it.get("file_path", "")
            images.append(
                {
                    "id": img_id,
                    "file_name": Path(file_path).name if file_path else item_id,
                    "width": it.get("width") or 0,
                    "height": it.get("height") or 0,
                }
            )

            r = result_map.get(item_id)
            if r is None:
                continue

            ann_str = r.get("annotation_json", "{}")
            try:
                ann = json.loads(ann_str)
            except Exception:
                ann = {}

            bboxes = _parse_bbox_from_shapes(ann.get("shapes", []))
            for bbox in bboxes:
                x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
                w = x2 - x1
                h = y2 - y1
                cat_id = label_to_cat_id.get(bbox["label"], 0)
                if cat_id == 0:
                    # 動態新增類別
                    cat_id = len(label_to_cat_id) + 1
                    label_to_cat_id[bbox["label"]] = cat_id
                    categories.append(
                        {
                            "id": cat_id,
                            "name": bbox["label"],
                            "supercategory": "none",
                        }
                    )

                annotations.append(
                    {
                        "id": ann_id,
                        "image_id": img_id,
                        "category_id": cat_id,
                        "bbox": [x1, y1, w, h],
                        "area": w * h,
                        "iscrowd": 0,
                    }
                )
                ann_id += 1

        coco_data = {
            "info": {"description": f"CIM Module 011 Export — {split_name}"},
            "images": images,
            "annotations": annotations,
            "categories": categories,
        }

        out_file = output_dir / f"{split_name}.json"
        out_file.write_text(
            json.dumps(coco_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        export_paths[split_name] = str(out_file)

    return export_paths


def export_yolo_txt(
    items: list[dict],
    results: list[dict],
    split_groups: dict[str, list[str]],
    output_dir: Path,
) -> dict[str, str]:
    """
    YOLO 格式匯出。
    - images/train/, images/val/, images/test/（複製圖片）
    - labels/train/, labels/val/, labels/test/（txt 標注）
    - classes.txt（標籤清單）
    YOLO 格式每行：<class_id> <cx> <cy> <w> <h>（0-1 normalized）
    回傳 {"train": "path/images/train", "val": ..., "test": ..., "classes_txt": ...}
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    item_map: dict[str, dict] = {it["item_id"]: it for it in items}
    result_map: dict[str, dict] = {r["item_id"]: r for r in results}

    # 蒐集所有標籤
    all_labels: list[str] = []
    seen_labels: set[str] = set()
    for r in results:
        ann_str = r.get("annotation_json", "{}")
        try:
            ann = json.loads(ann_str)
        except Exception:
            ann = {}
        for shape in ann.get("shapes", []):
            lbl = shape.get("label", "")
            if lbl and lbl not in seen_labels:
                seen_labels.add(lbl)
                all_labels.append(lbl)

    label_to_id = {lbl: idx for idx, lbl in enumerate(sorted(all_labels))}
    sorted_labels = sorted(all_labels)

    # 寫入 classes.txt
    classes_file = output_dir / "classes.txt"
    classes_file.write_text("\n".join(sorted_labels), encoding="utf-8")

    export_paths: dict[str, str] = {"classes_txt": str(classes_file)}

    for split_name, split_ids in split_groups.items():
        img_dir = output_dir / "images" / split_name
        lbl_dir = output_dir / "labels" / split_name
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)

        for item_id in split_ids:
            it = item_map.get(item_id)
            if it is None:
                continue

            file_path = it.get("file_path", "")
            img_width = it.get("width") or 0
            img_height = it.get("height") or 0

            # 複製圖片（若不存在則跳過，不 crash）
            if file_path:
                src_path = Path(file_path)
                if src_path.exists():
                    try:
                        shutil.copy2(str(src_path), str(img_dir / src_path.name))
                    except Exception:
                        pass  # 複製失敗，跳過

            # 產生 YOLO label txt
            r = result_map.get(item_id)
            if r is None:
                continue

            ann_str = r.get("annotation_json", "{}")
            try:
                ann = json.loads(ann_str)
            except Exception:
                ann = {}

            bboxes = _parse_bbox_from_shapes(ann.get("shapes", []))
            if not bboxes:
                continue

            stem = Path(file_path).stem if file_path else item_id
            lbl_lines: list[str] = []
            for bbox in bboxes:
                cls_id = label_to_id.get(bbox["label"], -1)
                if cls_id < 0:
                    # 動態加入（若 label 不在 sorted_labels 中）
                    cls_id = len(label_to_id)
                    label_to_id[bbox["label"]] = cls_id

                if img_width > 0 and img_height > 0:
                    cx = ((bbox["x1"] + bbox["x2"]) / 2) / img_width
                    cy = ((bbox["y1"] + bbox["y2"]) / 2) / img_height
                    bw = (bbox["x2"] - bbox["x1"]) / img_width
                    bh = (bbox["y2"] - bbox["y1"]) / img_height
                else:
                    # 若無寬高資訊，輸出原始像素值（無法 normalize）
                    cx = (bbox["x1"] + bbox["x2"]) / 2
                    cy = (bbox["y1"] + bbox["y2"]) / 2
                    bw = bbox["x2"] - bbox["x1"]
                    bh = bbox["y2"] - bbox["y1"]

                lbl_lines.append(
                    f"{cls_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"
                )

            lbl_file = lbl_dir / f"{stem}.txt"
            lbl_file.write_text("\n".join(lbl_lines), encoding="utf-8")

        export_paths[split_name] = str(img_dir)

    return export_paths


def export_csv(
    items: list[dict],
    results: list[dict],
    output_dir: Path,
) -> str:
    """
    單一 CSV 檔，欄位：item_id, file_path, label, confidence, x1, y1, x2, y2。
    回傳 CSV 檔案路徑。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    item_map: dict[str, dict] = {it["item_id"]: it for it in items}
    csv_path = output_dir / "annotations.csv"

    fieldnames = ["item_id", "file_path", "label", "confidence", "x1", "y1", "x2", "y2"]

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in results:
            item_id = r.get("item_id", "")
            it = item_map.get(item_id, {})
            file_path = it.get("file_path", "")
            confidence = r.get("confidence")

            ann_str = r.get("annotation_json", "{}")
            try:
                ann = json.loads(ann_str)
            except Exception:
                ann = {}

            bboxes = _parse_bbox_from_shapes(ann.get("shapes", []))

            if bboxes:
                for bbox in bboxes:
                    writer.writerow(
                        {
                            "item_id": item_id,
                            "file_path": file_path,
                            "label": bbox["label"],
                            "confidence": confidence if confidence is not None else "",
                            "x1": bbox["x1"],
                            "y1": bbox["y1"],
                            "x2": bbox["x2"],
                            "y2": bbox["y2"],
                        }
                    )
            else:
                # 無 bbox，仍輸出一行
                writer.writerow(
                    {
                        "item_id": item_id,
                        "file_path": file_path,
                        "label": r.get("label", ""),
                        "confidence": confidence if confidence is not None else "",
                        "x1": "",
                        "y1": "",
                        "x2": "",
                        "y2": "",
                    }
                )

    return str(csv_path)


# ─── 主流程 ───────────────────────────────────────────────────────────────────


def execute_logic(params: dict) -> dict:
    """
    執行 Result Sink 主流程。

    params:
        manifest_id: str
        run_id: str  （若空字串則自動新建 uuid）
        export_formats: list[str]  # ['coco_json', 'yolo_txt', 'csv']
        export_dir: str
        split_train: int  (e.g. 70)
        split_val: int    (e.g. 15)
        split_test: int   (e.g. 15)
        stratified: bool

    回傳包含 mode, run_id, manifest_name, 統計資訊, export_paths 等。
    """
    # 動態載入 _config（避免 package import 問題）
    _cfg_spec = _ilu.spec_from_file_location("module_011._config", _HERE / "_config.py")
    _cfg_mod = _ilu.module_from_spec(_cfg_spec)
    _cfg_spec.loader.exec_module(_cfg_mod)  # type: ignore[union-attr]

    import sys as _sys
    if "module_011._config" not in _sys.modules:
        _sys.modules["module_011._config"] = _cfg_mod
    else:
        # 若已被 monkeypatch，使用已存在的版本
        _cfg_mod = _sys.modules["module_011._config"]

    db_path = _cfg_mod.get_manifest_db_path()

    manifest_id: str = params.get("manifest_id", "")
    run_id: str = params.get("run_id", "").strip()
    export_formats: list[str] = params.get("export_formats", ["coco_json"])
    export_dir_str: str = params.get("export_dir", "")
    split_train: int = int(params.get("split_train", 70))
    split_val: int = int(params.get("split_val", 15))
    split_test: int = int(params.get("split_test", 15))
    stratified: bool = bool(params.get("stratified", True))

    # ── 1. 取得 manifest ──
    if not manifest_id:
        return {
            "mode": "error",
            "error": "manifest_id 不可為空",
            "run_id": run_id,
            "manifest_id": manifest_id,
            "manifest_name": "",
            "total_items": 0,
            "annotation_count": 0,
            "label_distribution": {},
            "split_counts": {"train": 0, "val": 0, "test": 0},
            "export_paths": {},
        }

    manifest = _mdb.get_manifest(db_path, manifest_id)
    if manifest is None:
        return {
            "mode": "error",
            "error": f"找不到 manifest: {manifest_id}",
            "run_id": run_id,
            "manifest_id": manifest_id,
            "manifest_name": "",
            "total_items": 0,
            "annotation_count": 0,
            "label_distribution": {},
            "split_counts": {"train": 0, "val": 0, "test": 0},
            "export_paths": {},
        }

    manifest_name: str = manifest.get("name", manifest_id)

    # ── 2. 自動產生 run_id ──
    if not run_id:
        run_id = str(uuid.uuid4())

    # ── 3. 取得 manifest items ──
    items = _mdb.get_manifest_items(db_path, manifest_id)
    total_items = len(items)

    # ── 4. 取得 annotation_results ──
    results = _mdb.get_annotation_results(db_path, run_id)
    annotation_count = len(results)

    # ── 5. 計算 label_distribution ──
    label_distribution: dict[str, int] = {}
    item_primary_labels: dict[str, str] = {}

    for r in results:
        ann_str = r.get("annotation_json", "{}")
        item_id = r.get("item_id", "")
        try:
            ann = json.loads(ann_str)
        except Exception:
            ann = {}

        bboxes = _parse_bbox_from_shapes(ann.get("shapes", []))
        for bbox in bboxes:
            lbl = bbox["label"]
            label_distribution[lbl] = label_distribution.get(lbl, 0) + 1
            if item_id not in item_primary_labels and lbl:
                item_primary_labels[item_id] = lbl

        # fallback：若無 shapes，用 label 欄位
        if not bboxes and r.get("label"):
            lbl = r["label"]
            label_distribution[lbl] = label_distribution.get(lbl, 0) + 1
            if item_id not in item_primary_labels:
                item_primary_labels[item_id] = lbl

    # ── 6. 計算 split ──
    total_pct = split_train + split_val + split_test
    if total_pct <= 0:
        total_pct = 100
    ratios = {
        "train": split_train / total_pct,
        "val": split_val / total_pct,
        "test": split_test / total_pct,
    }

    all_item_ids = [it["item_id"] for it in items]

    if stratified:
        split_groups = stratified_split(all_item_ids, item_primary_labels, ratios)
    else:
        split_groups = _random_split(all_item_ids, ratios)

    split_counts = {k: len(v) for k, v in split_groups.items()}

    # ── 7. 決定匯出目錄 ──
    if export_dir_str:
        export_base = Path(export_dir_str)
    else:
        export_base = _CIM_LOG_DIR / "exports" / run_id

    export_base.mkdir(parents=True, exist_ok=True)

    # ── 8. 依格式匯出 ──
    export_paths: dict = {}

    try:
        for fmt in export_formats:
            if fmt == "coco_json":
                coco_dir = export_base / "coco_json"
                paths = export_coco_json(items, results, split_groups, coco_dir)
                export_paths["coco_json"] = paths
                # 記錄到 DB
                _mdb.create_export_record(
                    db_path,
                    run_id,
                    manifest_id,
                    "coco_json",
                    str(coco_dir),
                    annotation_count,
                )

            elif fmt == "yolo_txt":
                yolo_dir = export_base / "yolo_txt"
                paths = export_yolo_txt(items, results, split_groups, yolo_dir)
                export_paths["yolo_txt"] = paths
                _mdb.create_export_record(
                    db_path,
                    run_id,
                    manifest_id,
                    "yolo_txt",
                    str(yolo_dir),
                    annotation_count,
                )

            elif fmt == "csv":
                csv_dir = export_base / "csv"
                csv_path = export_csv(items, results, csv_dir)
                export_paths["csv"] = csv_path
                _mdb.create_export_record(
                    db_path,
                    run_id,
                    manifest_id,
                    "csv",
                    csv_path,
                    annotation_count,
                )

    except Exception as exc:
        return {
            "mode": "error",
            "error": f"匯出失敗：{exc}",
            "run_id": run_id,
            "manifest_id": manifest_id,
            "manifest_name": manifest_name,
            "total_items": total_items,
            "annotation_count": annotation_count,
            "label_distribution": label_distribution,
            "split_counts": split_counts,
            "export_paths": export_paths,
        }

    return {
        "mode": "done",
        "error": None,
        "run_id": run_id,
        "manifest_id": manifest_id,
        "manifest_name": manifest_name,
        "total_items": total_items,
        "annotation_count": annotation_count,
        "label_distribution": label_distribution,
        "split_counts": split_counts,
        "export_paths": export_paths,
    }
