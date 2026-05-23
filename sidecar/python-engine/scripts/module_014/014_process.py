from __future__ import annotations

"""
014_process.py — Export 核心邏輯
無 Streamlit import。

支援格式：
  coco_json   — COCO Detection JSON（train/val/test）
  yolo_txt    — YOLO txt + data.yaml（images/ labels/ structure）
  pascal_voc  — Pascal VOC XML（Annotations/ JPEGImages/ ImageSets/）
  imagefolder — PyTorch ImageFolder（train/class/ structure，依分類標籤）
  csv         — Flat CSV（bbox + 分類）
"""

import csv
import importlib.util as _ilu
import json
import os
import random
import shutil
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NamedTuple

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_014_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_mdb_spec = _ilu.spec_from_file_location(
    "_manifest_db", _HERE.parent / "shared" / "_manifest_db.py"
)
_mdb = _ilu.module_from_spec(_mdb_spec)
_mdb_spec.loader.exec_module(_mdb)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CIM_LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", str(_PROJECT_ROOT / "tmp" / "cim_log")))


# ─── 驗證 ─────────────────────────────────────────────────────────────────────

class ValidationIssue(NamedTuple):
    severity: str   # "error" | "warning" | "info"
    code: str
    item_id: str
    message: str


def validate_pre_export(
    items: list[dict],
    shapes_map: dict[str, list[dict]],
    classifications: dict[str, str],
    export_formats: list[str],
) -> list[ValidationIssue]:
    """
    Run pre-export checks and return a list of ValidationIssues.

    Checks:
      - no_json_file: image has no annotation JSON at all (warning)
      - empty_shapes: JSON exists but contains no shapes (info)
      - invalid_bbox: shape has zero or negative area (error)
      - empty_label: shape has an empty label string (warning)
      - no_classification: imagefolder format requested but item has no classification (warning)
    """
    issues: list[ValidationIssue] = []
    need_clf = "imagefolder" in export_formats

    for it in items:
        iid = it["item_id"]
        fp = it.get("file_path", "")
        fname = Path(fp).name if fp else iid

        ann_path = Path(fp).with_suffix(".json") if fp else None
        has_json = ann_path is not None and ann_path.exists()

        if not has_json:
            issues.append(ValidationIssue(
                severity="warning",
                code="no_json_file",
                item_id=iid,
                message=f"{fname} 無標注 JSON，將以空標注匯出",
            ))
        else:
            shapes = shapes_map.get(iid, [])
            if not shapes:
                issues.append(ValidationIssue(
                    severity="info",
                    code="empty_shapes",
                    item_id=iid,
                    message=f"{fname} 的標注為空（無 shapes）",
                ))
            for s in shapes:
                if s.get("x2", 0) <= s.get("x1", 0) or s.get("y2", 0) <= s.get("y1", 0):
                    issues.append(ValidationIssue(
                        severity="error",
                        code="invalid_bbox",
                        item_id=iid,
                        message=f"{fname} 包含面積為零或負的 BBox（label={s.get('label', '')}）",
                    ))
                if not s.get("label", "").strip():
                    issues.append(ValidationIssue(
                        severity="warning",
                        code="empty_label",
                        item_id=iid,
                        message=f"{fname} 包含空標籤的 shape",
                    ))

        if need_clf and not classifications.get(iid, "").strip():
            issues.append(ValidationIssue(
                severity="warning",
                code="no_classification",
                item_id=iid,
                message=f"{fname} 匯出 imagefolder 格式時無分類標籤，將被略過",
            ))

    return issues


# ─── 資料結構輔助 ──────────────────────────────────────────────────────────────

def _load_xany_annotation(file_path: str) -> dict:
    """讀取 X-AnyLabeling JSON（與影像同名同目錄）。"""
    if not file_path:
        return {}
    ann_path = Path(file_path).with_suffix(".json")
    if not ann_path.exists():
        return {}
    try:
        return json.loads(ann_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _parse_shapes(shapes: list[dict]) -> list[dict]:
    """
    解析 X-AnyLabeling shapes，回傳 normalized bbox list。
    每筆：{"label": str, "x1": float, "y1": float, "x2": float, "y2": float,
            "shape_type": str, "polygon_pts": [[x,y],...]}
    只處理 rectangle / polygon；跳過 point / line。
    """
    results: list[dict] = []
    for shape in shapes:
        label = shape.get("label", "")
        points = shape.get("points", [])
        shape_type = shape.get("shape_type", "")

        if shape_type == "rectangle" and len(points) >= 2:
            xs = [p[0] for p in points if len(p) >= 2]
            ys = [p[1] for p in points if len(p) >= 2]
            if xs and ys:
                results.append({
                    "label": label,
                    "x1": float(min(xs)),
                    "y1": float(min(ys)),
                    "x2": float(max(xs)),
                    "y2": float(max(ys)),
                    "shape_type": "rectangle",
                    "polygon_pts": [],
                })
        elif shape_type == "polygon" and len(points) >= 3:
            xs = [p[0] for p in points if len(p) >= 2]
            ys = [p[1] for p in points if len(p) >= 2]
            if xs and ys:
                results.append({
                    "label": label,
                    "x1": float(min(xs)),
                    "y1": float(min(ys)),
                    "x2": float(max(xs)),
                    "y2": float(max(ys)),
                    "shape_type": "polygon",
                    "polygon_pts": [[p[0], p[1]] for p in points if len(p) >= 2],
                })
    return results


# ─── Split 邏輯 ────────────────────────────────────────────────────────────────

def _stratified_split(
    item_ids: list[str],
    item_labels: dict[str, str],
    ratios: dict,
) -> dict[str, list[str]]:
    if not item_ids:
        return {"train": [], "val": [], "test": []}

    train_r = ratios.get("train", 0.7)
    val_r = ratios.get("val", 0.15)

    label_groups: dict[str, list[str]] = {}
    for iid in item_ids:
        lbl = item_labels.get(iid, "__unknown__")
        label_groups.setdefault(lbl, []).append(iid)

    train_ids: list[str] = []
    val_ids: list[str] = []
    test_ids: list[str] = []

    for ids in label_groups.values():
        shuffled = ids[:]
        random.shuffle(shuffled)
        n = len(shuffled)
        if n < 3:
            train_ids.extend(shuffled)
            continue
        n_train = max(1, round(n * train_r))
        n_val = max(0, round(n * val_r))
        if n_train + n_val >= n:
            n_val = max(0, n - n_train - 1)
        train_ids.extend(shuffled[:n_train])
        val_ids.extend(shuffled[n_train: n_train + n_val])
        test_ids.extend(shuffled[n_train + n_val:])

    return {"train": train_ids, "val": val_ids, "test": test_ids}


def _random_split(item_ids: list[str], ratios: dict) -> dict[str, list[str]]:
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
        "val": shuffled[n_train: n_train + n_val],
        "test": shuffled[n_train + n_val:],
    }


# ─── 匯出：COCO JSON ───────────────────────────────────────────────────────────

def export_coco_json(
    items: list[dict],
    shapes_map: dict[str, list[dict]],
    split_groups: dict[str, list[str]],
    output_dir: Path,
) -> dict[str, str]:
    """
    COCO Detection JSON。
    支援 rectangle（bbox）和 polygon（segmentation）。
    輸出：train.json, val.json, test.json
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    item_map = {it["item_id"]: it for it in items}

    all_labels: set[str] = set()
    for shapes in shapes_map.values():
        for s in shapes:
            if s["label"]:
                all_labels.add(s["label"])

    sorted_labels = sorted(all_labels)
    categories = [
        {"id": i + 1, "name": lbl, "supercategory": "none"}
        for i, lbl in enumerate(sorted_labels)
    ]
    label_to_cat = {lbl: i + 1 for i, lbl in enumerate(sorted_labels)}

    export_paths: dict[str, str] = {}
    for split_name, split_ids in split_groups.items():
        images_list = []
        annotations_list = []
        ann_id = 1

        for img_id, item_id in enumerate(split_ids, start=1):
            it = item_map.get(item_id)
            if it is None:
                continue
            fp = it.get("file_path", "")
            w = it.get("width") or 0
            h = it.get("height") or 0
            images_list.append({
                "id": img_id,
                "file_name": Path(fp).name if fp else item_id,
                "width": w,
                "height": h,
            })

            for shape in shapes_map.get(item_id, []):
                x1, y1, x2, y2 = shape["x1"], shape["y1"], shape["x2"], shape["y2"]
                bw, bh = x2 - x1, y2 - y1
                cat_id = label_to_cat.get(shape["label"])
                if cat_id is None:
                    cat_id = len(label_to_cat) + 1
                    label_to_cat[shape["label"]] = cat_id
                    categories.append({
                        "id": cat_id, "name": shape["label"], "supercategory": "none"
                    })

                ann = {
                    "id": ann_id,
                    "image_id": img_id,
                    "category_id": cat_id,
                    "bbox": [x1, y1, bw, bh],
                    "area": bw * bh,
                    "iscrowd": 0,
                }
                if shape["shape_type"] == "polygon" and shape["polygon_pts"]:
                    flat = [coord for pt in shape["polygon_pts"] for coord in pt]
                    ann["segmentation"] = [flat]
                annotations_list.append(ann)
                ann_id += 1

        out_file = output_dir / f"{split_name}.json"
        out_file.write_text(
            json.dumps({
                "info": {"description": f"CIM Export — {split_name}"},
                "images": images_list,
                "annotations": annotations_list,
                "categories": categories,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        export_paths[split_name] = str(out_file)

    return export_paths


# ─── 匯出：YOLO txt ────────────────────────────────────────────────────────────

def export_yolo_txt(
    items: list[dict],
    shapes_map: dict[str, list[dict]],
    split_groups: dict[str, list[str]],
    output_dir: Path,
) -> dict[str, str]:
    """
    YOLO txt（normalized cx cy w h）+ data.yaml。
    只處理 rectangle（bbox）；polygon 取 bounding box 近似。
    結構：images/train/, labels/train/, classes.txt, data.yaml
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    item_map = {it["item_id"]: it for it in items}

    all_labels: list[str] = []
    seen: set[str] = set()
    for shapes in shapes_map.values():
        for s in shapes:
            if s["label"] and s["label"] not in seen:
                seen.add(s["label"])
                all_labels.append(s["label"])
    sorted_labels = sorted(all_labels)
    label_to_id = {lbl: i for i, lbl in enumerate(sorted_labels)}

    # classes.txt
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
            fp = it.get("file_path", "")
            iw = it.get("width") or 0
            ih = it.get("height") or 0

            if fp and Path(fp).exists():
                try:
                    shutil.copy2(fp, str(img_dir / Path(fp).name))
                except Exception:
                    pass

            shapes = shapes_map.get(item_id, [])
            if not shapes:
                continue

            stem = Path(fp).stem if fp else item_id
            lines: list[str] = []
            for s in shapes:
                cls_id = label_to_id.get(s["label"], -1)
                if cls_id < 0:
                    cls_id = len(label_to_id)
                    label_to_id[s["label"]] = cls_id
                if iw > 0 and ih > 0:
                    cx = ((s["x1"] + s["x2"]) / 2) / iw
                    cy = ((s["y1"] + s["y2"]) / 2) / ih
                    bw = (s["x2"] - s["x1"]) / iw
                    bh = (s["y2"] - s["y1"]) / ih
                else:
                    cx = (s["x1"] + s["x2"]) / 2
                    cy = (s["y1"] + s["y2"]) / 2
                    bw = s["x2"] - s["x1"]
                    bh = s["y2"] - s["y1"]
                lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")

            (lbl_dir / f"{stem}.txt").write_text("\n".join(lines), encoding="utf-8")

        export_paths[split_name] = str(img_dir)

    # data.yaml
    yaml_content = (
        f"path: {output_dir}\n"
        f"train: images/train\n"
        f"val: images/val\n"
        f"test: images/test\n"
        f"nc: {len(sorted_labels)}\n"
        f"names: {json.dumps(sorted_labels, ensure_ascii=False)}\n"
    )
    yaml_file = output_dir / "data.yaml"
    yaml_file.write_text(yaml_content, encoding="utf-8")
    export_paths["data_yaml"] = str(yaml_file)

    return export_paths


# ─── 匯出：Pascal VOC XML ──────────────────────────────────────────────────────

def export_pascal_voc(
    items: list[dict],
    shapes_map: dict[str, list[dict]],
    split_groups: dict[str, list[str]],
    output_dir: Path,
) -> dict[str, str]:
    """
    Pascal VOC XML 格式。
    結構：
      Annotations/<stem>.xml
      JPEGImages/<filename>（複製）
      ImageSets/Main/train.txt, val.txt, test.txt
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    ann_dir = output_dir / "Annotations"
    img_dir = output_dir / "JPEGImages"
    sets_dir = output_dir / "ImageSets" / "Main"
    ann_dir.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)
    sets_dir.mkdir(parents=True, exist_ok=True)

    item_map = {it["item_id"]: it for it in items}
    export_paths: dict[str, str] = {}

    for split_name, split_ids in split_groups.items():
        stem_list: list[str] = []

        for item_id in split_ids:
            it = item_map.get(item_id)
            if it is None:
                continue
            fp = it.get("file_path", "")
            iw = it.get("width") or 0
            ih = it.get("height") or 0
            fname = Path(fp).name if fp else f"{item_id}.jpg"
            stem = Path(fp).stem if fp else item_id
            stem_list.append(stem)

            # 複製圖片
            if fp and Path(fp).exists():
                try:
                    shutil.copy2(fp, str(img_dir / fname))
                except Exception:
                    pass

            # 產生 XML
            annotation = ET.Element("annotation")
            ET.SubElement(annotation, "folder").text = "JPEGImages"
            ET.SubElement(annotation, "filename").text = fname
            size_el = ET.SubElement(annotation, "size")
            ET.SubElement(size_el, "width").text = str(iw)
            ET.SubElement(size_el, "height").text = str(ih)
            ET.SubElement(size_el, "depth").text = "3"
            ET.SubElement(annotation, "segmented").text = "0"

            for s in shapes_map.get(item_id, []):
                obj = ET.SubElement(annotation, "object")
                ET.SubElement(obj, "name").text = s["label"]
                ET.SubElement(obj, "pose").text = "Unspecified"
                ET.SubElement(obj, "truncated").text = "0"
                ET.SubElement(obj, "difficult").text = "0"
                bndbox = ET.SubElement(obj, "bndbox")
                ET.SubElement(bndbox, "xmin").text = str(int(s["x1"]))
                ET.SubElement(bndbox, "ymin").text = str(int(s["y1"]))
                ET.SubElement(bndbox, "xmax").text = str(int(s["x2"]))
                ET.SubElement(bndbox, "ymax").text = str(int(s["y2"]))

            tree = ET.ElementTree(annotation)
            ET.indent(tree, space="  ")
            xml_path = ann_dir / f"{stem}.xml"
            tree.write(str(xml_path), encoding="utf-8", xml_declaration=True)

        # ImageSets/Main/<split>.txt
        set_file = sets_dir / f"{split_name}.txt"
        set_file.write_text("\n".join(stem_list), encoding="utf-8")
        export_paths[split_name] = str(set_file)

    export_paths["annotations_dir"] = str(ann_dir)
    export_paths["images_dir"] = str(img_dir)
    return export_paths


# ─── 匯出：ImageFolder（分類） ─────────────────────────────────────────────────

def export_imagefolder(
    items: list[dict],
    classifications: dict[str, str],
    split_groups: dict[str, list[str]],
    output_dir: Path,
) -> dict[str, str]:
    """
    PyTorch ImageFolder 格式（依分類標籤）。
    結構：
      train/cat/img001.jpg
      val/dog/img002.jpg
      test/cat/img003.jpg
    classifications: {item_id → label}
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    item_map = {it["item_id"]: it for it in items}
    export_paths: dict[str, str] = {}
    copied = 0
    skipped = 0

    for split_name, split_ids in split_groups.items():
        split_dir = output_dir / split_name
        split_dir.mkdir(parents=True, exist_ok=True)
        export_paths[split_name] = str(split_dir)

        for item_id in split_ids:
            it = item_map.get(item_id)
            if it is None:
                continue
            fp = it.get("file_path", "")
            fname = Path(fp).name if fp else ""
            label = classifications.get(item_id, "")
            if not label or not fp or not fname:
                skipped += 1
                continue

            safe_label = label.replace("/", "_").replace("\\", "_").strip()
            class_dir = split_dir / safe_label
            class_dir.mkdir(parents=True, exist_ok=True)
            src = Path(fp)
            if src.exists():
                try:
                    shutil.copy2(str(src), str(class_dir / fname))
                    copied += 1
                except Exception:
                    skipped += 1
            else:
                skipped += 1

    export_paths["_copied"] = str(copied)
    export_paths["_skipped"] = str(skipped)
    return export_paths


# ─── 匯出：CSV ────────────────────────────────────────────────────────────────

def export_csv(
    items: list[dict],
    shapes_map: dict[str, list[dict]],
    classifications: dict[str, str],
    output_dir: Path,
) -> str:
    """
    Flat CSV：item_id, file_path, split, classification, label, x1, y1, x2, y2
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    item_map = {it["item_id"]: it for it in items}
    csv_path = output_dir / "annotations.csv"
    fieldnames = ["item_id", "file_path", "split", "classification",
                  "label", "shape_type", "x1", "y1", "x2", "y2"]

    # split 查找表（由 execute_logic 傳入前不知道，改為空字串）
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for item_id, it in item_map.items():
            fp = it.get("file_path", "")
            clf_label = classifications.get(item_id, "")
            shapes = shapes_map.get(item_id, [])

            if shapes:
                for s in shapes:
                    writer.writerow({
                        "item_id": item_id,
                        "file_path": fp,
                        "split": "",
                        "classification": clf_label,
                        "label": s["label"],
                        "shape_type": s["shape_type"],
                        "x1": f"{s['x1']:.2f}",
                        "y1": f"{s['y1']:.2f}",
                        "x2": f"{s['x2']:.2f}",
                        "y2": f"{s['y2']:.2f}",
                    })
            else:
                writer.writerow({
                    "item_id": item_id,
                    "file_path": fp,
                    "split": "",
                    "classification": clf_label,
                    "label": "",
                    "shape_type": "",
                    "x1": "", "y1": "", "x2": "", "y2": "",
                })

    return str(csv_path)


def _fill_csv_split(csv_path: str, split_groups: dict[str, list[str]]) -> None:
    """將 split 欄位填入 CSV（二次掃描）。"""
    item_to_split: dict[str, str] = {}
    for split_name, ids in split_groups.items():
        for iid in ids:
            item_to_split[iid] = split_name

    rows: list[dict] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        for row in reader:
            row["split"] = item_to_split.get(row.get("item_id", ""), "")
            rows.append(row)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ─── 主流程 ───────────────────────────────────────────────────────────────────

def execute_logic(params: dict) -> dict:
    """
    params:
        manifest_id: str
        export_formats: list[str]
        export_dir: str
        split_train: int
        split_val: int
        split_test: int
        stratified: bool
    """
    manifest_id: str = params.get("manifest_id", "")
    export_formats: list[str] = params.get("export_formats", ["coco_json"])
    export_dir_str: str = params.get("export_dir", "")
    enable_split: bool = bool(params.get("enable_split", False))
    split_train: int = int(params.get("split_train", 100))
    split_val: int = int(params.get("split_val", 0))
    split_test: int = int(params.get("split_test", 0))
    stratified: bool = bool(params.get("stratified", False))

    _base = {
        "manifest_id": manifest_id,
        "total_items": 0,
        "annotated_items": 0,
        "classified_items": 0,
        "label_counts": {},
        "classification_counts": {},
        "split_counts": {"train": 0, "val": 0, "test": 0},
        "export_formats": export_formats,
        "export_dir": export_dir_str,
        "export_paths": {},
    }

    if not manifest_id:
        return {**_base, "mode": "error", "error": "未選擇 Manifest"}

    db_path = _cfg.get_manifest_db_path()
    manifest = _mdb.get_manifest(db_path, manifest_id)
    if manifest is None:
        return {**_base, "mode": "error", "error": f"找不到 Manifest：{manifest_id}"}

    # ── 1. 取得 manifest items ──────────────────────────────────────────────
    items = _mdb.get_manifest_items(db_path, manifest_id)
    total_items = len(items)
    _base["total_items"] = total_items

    # ── 2. 讀取分類結果 ─────────────────────────────────────────────────────
    classifications = _cfg.load_classifications(manifest_id)
    classified_items = sum(1 for it in items if classifications.get(it["item_id"]))
    _base["classified_items"] = classified_items

    classification_counts: dict[str, int] = {}
    for iid, lbl in classifications.items():
        if lbl:
            classification_counts[lbl] = classification_counts.get(lbl, 0) + 1
    _base["classification_counts"] = classification_counts

    # ── 3. 讀取 X-AnyLabeling 標注 ─────────────────────────────────────────
    shapes_map: dict[str, list[dict]] = {}
    label_counts: dict[str, int] = {}
    for it in items:
        iid = it["item_id"]
        ann = _load_xany_annotation(it.get("file_path", ""))
        shapes = _parse_shapes(ann.get("shapes", []))
        shapes_map[iid] = shapes
        for s in shapes:
            label_counts[s["label"]] = label_counts.get(s["label"], 0) + 1

    annotated_items = sum(1 for iid, sh in shapes_map.items() if sh)
    _base["annotated_items"] = annotated_items
    _base["label_counts"] = label_counts

    # ── 4. Split ────────────────────────────────────────────────────────────
    all_ids = [it["item_id"] for it in items]

    if not enable_split:
        # 不分割：全部放進 "all" 群組，各格式 exporter 會用 "all" 當目錄名
        split_groups = {"all": all_ids}
    else:
        total_pct = split_train + split_val + split_test
        if total_pct <= 0:
            total_pct = 100
        ratios = {
            "train": split_train / total_pct,
            "val": split_val / total_pct,
            "test": split_test / total_pct,
        }
        item_primary_labels = {iid: classifications.get(iid, "") for iid in all_ids}
        if stratified:
            split_groups = _stratified_split(all_ids, item_primary_labels, ratios)
        else:
            split_groups = _random_split(all_ids, ratios)

    _base["split_counts"] = {k: len(v) for k, v in split_groups.items()}

    # ── 5. 驗證 ─────────────────────────────────────────────────────────────
    validation_issues = validate_pre_export(items, shapes_map, classifications, export_formats)
    _base["validation_issues"] = [
        {"severity": vi.severity, "code": vi.code, "item_id": vi.item_id, "message": vi.message}
        for vi in validation_issues
    ]
    # Block export if any errors exist
    has_errors = any(vi.severity == "error" for vi in validation_issues)
    if has_errors:
        return {**_base, "mode": "validation_error",
                "error": f"發現 {sum(1 for v in validation_issues if v.severity == 'error')} 個錯誤，請修正後再匯出"}

    # ── 7. 匯出目錄 ─────────────────────────────────────────────────────────
    export_base = Path(export_dir_str) if export_dir_str else _cfg.get_default_export_dir(manifest_id)
    export_base.mkdir(parents=True, exist_ok=True)
    _base["export_dir"] = str(export_base)

    # ── 8. 各格式匯出 ───────────────────────────────────────────────────────
    export_paths: dict = {}
    try:
        for fmt in export_formats:
            if fmt == "coco_json":
                paths = export_coco_json(items, shapes_map, split_groups,
                                         export_base / "coco_json")
                export_paths["coco_json"] = paths
                _mdb.create_export_record(
                    db_path, str(uuid.uuid4()), manifest_id,
                    "coco_json", str(export_base / "coco_json"), annotated_items,
                )

            elif fmt == "yolo_txt":
                paths = export_yolo_txt(items, shapes_map, split_groups,
                                        export_base / "yolo_txt")
                export_paths["yolo_txt"] = paths
                _mdb.create_export_record(
                    db_path, str(uuid.uuid4()), manifest_id,
                    "yolo_txt", str(export_base / "yolo_txt"), annotated_items,
                )

            elif fmt == "pascal_voc":
                paths = export_pascal_voc(items, shapes_map, split_groups,
                                          export_base / "pascal_voc")
                export_paths["pascal_voc"] = paths
                _mdb.create_export_record(
                    db_path, str(uuid.uuid4()), manifest_id,
                    "pascal_voc", str(export_base / "pascal_voc"), annotated_items,
                )

            elif fmt == "imagefolder":
                paths = export_imagefolder(items, classifications, split_groups,
                                           export_base / "imagefolder")
                export_paths["imagefolder"] = paths
                _mdb.create_export_record(
                    db_path, str(uuid.uuid4()), manifest_id,
                    "imagefolder", str(export_base / "imagefolder"), classified_items,
                )

            elif fmt == "csv":
                csv_path = export_csv(items, shapes_map, classifications,
                                      export_base / "csv")
                _fill_csv_split(csv_path, split_groups)
                export_paths["csv"] = csv_path
                _mdb.create_export_record(
                    db_path, str(uuid.uuid4()), manifest_id,
                    "csv", csv_path, total_items,
                )

    except Exception as exc:
        return {**_base, "mode": "error", "error": f"匯出失敗：{exc}",
                "export_paths": export_paths}

    return {**_base, "mode": "done", "error": None, "export_paths": export_paths}
