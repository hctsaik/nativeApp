from __future__ import annotations

"""
013_process.py — Sync Back to Service 核心邏輯
無 Streamlit import。

流程：
  1. 組裝 items + shapes_map + classifications
  2. validation（block on error）
  3. 依 scope 篩選送出項目
  4. 切 chunk（每 100 筆）→ POST /datasets/{id}/submissions（逐 chunk）
  5. 在記憶體產生格式 zip → POST /datasets/{id}/submissions/{submit_id}/exports
  6. 寫入 sync_state + sync_history
"""

import importlib.util as _ilu
import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple
import urllib.request
import urllib.error

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_013_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_mdb_spec = _ilu.spec_from_file_location(
    "_manifest_db", _HERE.parent / "shared" / "_manifest_db.py"
)
_mdb = _ilu.module_from_spec(_mdb_spec)
_mdb_spec.loader.exec_module(_mdb)

_p14_spec = _ilu.spec_from_file_location(
    "_014_process", _HERE.parent / "module_014" / "014_process.py"
)
_p14 = _ilu.module_from_spec(_p14_spec)
_p14_spec.loader.exec_module(_p14)

CHUNK_SIZE = 100


# ─── 驗證 ─────────────────────────────────────────────────────────────────────

class ValidationIssue(NamedTuple):
    severity: str   # "error" | "warning" | "info"
    code: str
    item_id: str
    message: str


def validate_pre_sync(
    items: list[dict],
    shapes_map: dict[str, list[dict]],
    classifications: dict[str, str],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for it in items:
        iid = it["item_id"]
        fp = it.get("file_path", "")
        fname = Path(fp).name if fp else iid

        for s in shapes_map.get(iid, []):
            if s.get("x2", 0) <= s.get("x1", 0) or s.get("y2", 0) <= s.get("y1", 0):
                issues.append(ValidationIssue(
                    severity="error",
                    code="invalid_bbox",
                    item_id=iid,
                    message=f"{fname} 包含面積為零或負的 BBox（label={s.get('label', '')}）",
                ))
            if not s.get("label", "").strip():
                issues.append(ValidationIssue(
                    severity="error",
                    code="empty_label",
                    item_id=iid,
                    message=f"{fname} 包含空標籤的 shape",
                ))

    empty_count = sum(
        1 for it in items
        if not shapes_map.get(it["item_id"]) and not classifications.get(it["item_id"], "")
    )
    if items and empty_count / len(items) > 0.30:
        issues.append(ValidationIssue(
            severity="warning",
            code="high_empty_ratio",
            item_id="",
            message=f"{empty_count}/{len(items)} 張（{empty_count/len(items)*100:.0f}%）完全無標注也無分類",
        ))

    return issues


# ─── 格式 zip 產生（記憶體） ───────────────────────────────────────────────────

def _build_coco_zip(
    items: list[dict],
    shapes_map: dict[str, list[dict]],
) -> bytes:
    all_labels: list[str] = sorted({
        s["label"]
        for shapes in shapes_map.values()
        for s in shapes
        if s["label"]
    })
    label_to_cat = {lbl: i + 1 for i, lbl in enumerate(all_labels)}
    categories = [
        {"id": i + 1, "name": lbl, "supercategory": "none"}
        for i, lbl in enumerate(all_labels)
    ]

    item_map = {it["item_id"]: it for it in items}
    images_list: list[dict] = []
    annotations_list: list[dict] = []
    ann_id = 1
    for img_id, it in enumerate(items, start=1):
        iid = it["item_id"]
        fp = it.get("file_path", "")
        images_list.append({
            "id": img_id,
            "file_name": Path(fp).name if fp else iid,
            "width": it.get("width") or 0,
            "height": it.get("height") or 0,
        })
        for shape in shapes_map.get(iid, []):
            x1, y1, x2, y2 = shape["x1"], shape["y1"], shape["x2"], shape["y2"]
            bw, bh = x2 - x1, y2 - y1
            cat_id = label_to_cat.get(shape["label"], len(label_to_cat) + 1)
            ann: dict = {
                "id": ann_id,
                "image_id": img_id,
                "category_id": cat_id,
                "bbox": [x1, y1, bw, bh],
                "area": bw * bh,
                "iscrowd": 0,
            }
            if shape["shape_type"] == "polygon" and shape.get("polygon_pts"):
                ann["segmentation"] = [[c for pt in shape["polygon_pts"] for c in pt]]
            annotations_list.append(ann)
            ann_id += 1

    coco_obj = {
        "info": {"description": "CIM Sync Back"},
        "images": images_list,
        "annotations": annotations_list,
        "categories": categories,
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("annotations.json", json.dumps(coco_obj, ensure_ascii=False, indent=2))
    buf.seek(0)
    return buf.read()


def _build_yolo_zip(
    items: list[dict],
    shapes_map: dict[str, list[dict]],
) -> bytes:
    all_labels = sorted({
        s["label"]
        for shapes in shapes_map.values()
        for s in shapes
        if s["label"]
    })
    label_to_id = {lbl: i for i, lbl in enumerate(all_labels)}
    nc = len(all_labels)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("classes.txt", "\n".join(all_labels))
        zf.writestr(
            "data.yaml",
            f"nc: {nc}\nnames: {json.dumps(all_labels, ensure_ascii=False)}\n",
        )
        for it in items:
            iid = it["item_id"]
            fp = it.get("file_path", "")
            iw = it.get("width") or 0
            ih = it.get("height") or 0
            stem = Path(fp).stem if fp else iid
            shapes = shapes_map.get(iid, [])
            if not shapes:
                continue
            lines: list[str] = []
            for s in shapes:
                cls_id = label_to_id.get(s["label"], nc)
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
            zf.writestr(f"labels/{stem}.txt", "\n".join(lines))
    buf.seek(0)
    return buf.read()


def _build_format_zip(
    fmt: str,
    items: list[dict],
    shapes_map: dict[str, list[dict]],
) -> bytes | None:
    if fmt == "coco_json":
        return _build_coco_zip(items, shapes_map)
    if fmt == "yolo_txt":
        return _build_yolo_zip(items, shapes_map)
    return None


# ─── HTTP 呼叫（無第三方依賴） ─────────────────────────────────────────────────

def _post_json(url: str, payload: dict, timeout: int = 30) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body}") from e


def _post_multipart(
    url: str,
    form_fields: dict[str, str],
    file_bytes: bytes,
    file_field: str,
    filename: str,
    timeout: int = 60,
) -> dict:
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for key, val in form_fields.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{val}\r\n".encode()
        )
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{filename}\"\r\nContent-Type: application/zip\r\n\r\n".encode()
        + file_bytes
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)

    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_r = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body_r}") from e


# ─── 主流程 ───────────────────────────────────────────────────────────────────

def execute_logic(params: dict) -> dict:
    """
    params:
        manifest_id:   str
        dataset_id:    str   (auto-composed: system_data_type_YYYYMMDD)
        service_url:   str   (base URL)
        scope:         "full" | "partial"
        export_format: "coco_json" | "yolo_txt" | "none"
        system_name:   str   (e.g. "iWISC", "SMM")
        data_type:     str   (e.g. "Simulation", "Issue", "Retrain")
        nt_account:    str
        timestamp:     str   (YYYY-MM-DD HH:MM:SS)
        description:   str
    """
    manifest_id: str = params.get("manifest_id", "")
    dataset_id: str = params.get("dataset_id", "")
    service_url: str = params.get("service_url", "").rstrip("/")
    scope: str = params.get("scope", "full")
    export_format: str = params.get("export_format", "none")
    upload_meta: dict = {
        "system_name": params.get("system_name", ""),
        "data_type": params.get("data_type", ""),
        "nt_account": params.get("nt_account", ""),
        "timestamp": params.get("timestamp", ""),
        "description": params.get("description", ""),
    }

    _base: dict = {
        "manifest_id": manifest_id,
        "dataset_id": dataset_id,
        "submit_id": "",
        "scope": scope,
        "scope_count": 0,
        "ok_count": 0,
        "failed_count": 0,
        "chunk_results": [],
        "export_format": export_format,
        "export_upload_status": "",
        "validation_issues": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": "",
    }

    if not manifest_id:
        return {**_base, "mode": "error", "error": "未選擇 Manifest"}
    if not dataset_id:
        return {**_base, "mode": "error", "error": "未填寫資料集 ID"}
    if not service_url:
        return {**_base, "mode": "error", "error": "未填寫 Service URL"}

    db_path = _cfg.get_manifest_db_path()
    manifest = _mdb.get_manifest(db_path, manifest_id)
    if manifest is None:
        return {**_base, "mode": "error", "error": f"找不到 Manifest：{manifest_id}"}

    # ── 1. 組裝資料 ───────────────────────────────────────────────────────────
    items = _mdb.get_manifest_items(db_path, manifest_id)
    classifications = _cfg.load_classifications(manifest_id)

    shapes_map: dict[str, list[dict]] = {}
    for it in items:
        iid = it["item_id"]
        ann = _p14._load_xany_annotation(it.get("file_path", ""))
        shapes_map[iid] = _p14._parse_shapes(ann.get("shapes", []))

    # ── 1b. Pre-sync snapshot ─────────────────────────────────────────────────
    try:
        snap_rows: list[dict] = []
        for it in items:
            fp = it.get("file_path", "")
            ann_p = Path(fp).with_suffix(".json") if fp else None
            if ann_p and ann_p.exists():
                try:
                    label_json = ann_p.read_text(encoding="utf-8")
                except Exception:
                    label_json = "{}"
                snap_rows.append({
                    "item_id": it["item_id"],
                    "trigger": "pre_sync",
                    "label_json": label_json,
                    "annotator_id": upload_meta.get("nt_account"),
                })
        if snap_rows:
            _mdb.save_snapshots_bulk(db_path, manifest_id, snap_rows)
    except Exception:
        pass  # snapshot failure must not block sync

    # ── 2. 驗證 ───────────────────────────────────────────────────────────────
    validation_issues = validate_pre_sync(items, shapes_map, classifications)
    _base["validation_issues"] = [
        {"severity": vi.severity, "code": vi.code, "item_id": vi.item_id, "message": vi.message}
        for vi in validation_issues
    ]
    if any(vi.severity == "error" for vi in validation_issues):
        err_n = sum(1 for vi in validation_issues if vi.severity == "error")
        return {**_base, "mode": "validation_error",
                "error": f"發現 {err_n} 個錯誤，請修正後再送出"}

    # ── 3. scope 篩選 ─────────────────────────────────────────────────────────
    if scope == "partial":
        send_items = [
            it for it in items
            if shapes_map.get(it["item_id"]) or classifications.get(it["item_id"], "")
        ]
    else:
        send_items = list(items)

    if not send_items:
        return {**_base, "mode": "error", "error": "沒有可送出的項目（scope=partial 但無已標注項）"}

    _base["scope_count"] = len(send_items)

    # ── 4. 送出 (chunks) ──────────────────────────────────────────────────────
    submit_id = str(uuid.uuid4())
    _base["submit_id"] = submit_id

    chunks = [send_items[i:i + CHUNK_SIZE] for i in range(0, len(send_items), CHUNK_SIZE)]
    total_chunks = len(chunks)
    chunk_results: list[dict] = []
    ok_count = 0
    failed_count = 0

    sync_state = _cfg.load_sync_state(manifest_id)
    item_states: dict = sync_state.get("items", {})

    submit_url = f"{service_url}/api/v1/datasets/{dataset_id}/submissions"

    for ci, chunk in enumerate(chunks):
        now_iso = datetime.now(timezone.utc).isoformat()
        payload_items = []
        for it in chunk:
            iid = it["item_id"]
            payload_items.append({
                "item_id": iid,
                "file_name": Path(it.get("file_path", iid)).name,
                "classification": classifications.get(iid, ""),
                "shapes": [
                    {
                        "label": s["label"],
                        "shape_type": s["shape_type"],
                        "x1": s["x1"], "y1": s["y1"],
                        "x2": s["x2"], "y2": s["y2"],
                        "polygon_pts": s.get("polygon_pts", []),
                    }
                    for s in shapes_map.get(iid, [])
                ],
            })

        payload = {
            "submit_id": submit_id,
            "scope": scope,
            "chunk_index": ci,
            "total_chunks": total_chunks,
            "metadata": upload_meta,
            "items": payload_items,
        }

        try:
            _post_json(submit_url, payload)
            for it in chunk:
                item_states[it["item_id"]] = {
                    "status": "ok",
                    "submit_id": submit_id,
                    "synced_at": now_iso,
                }
            chunk_results.append({"chunk": ci, "status": "ok", "count": len(chunk)})
            ok_count += len(chunk)
        except Exception as exc:
            err_msg = str(exc)
            for it in chunk:
                item_states[it["item_id"]] = {
                    "status": "failed",
                    "submit_id": submit_id,
                    "error": err_msg,
                }
            chunk_results.append({"chunk": ci, "status": "failed", "count": len(chunk), "error": err_msg})
            failed_count += len(chunk)

    sync_state["items"] = item_states
    _cfg.save_sync_state(manifest_id, sync_state)

    _base["ok_count"] = ok_count
    _base["failed_count"] = failed_count
    _base["chunk_results"] = chunk_results

    # ── 5. 格式包上傳 ─────────────────────────────────────────────────────────
    export_upload_status = "skipped"
    if export_format != "none" and ok_count > 0:
        try:
            zip_bytes = _build_format_zip(export_format, send_items, shapes_map)
            if zip_bytes:
                export_url = (
                    f"{service_url}/api/v1/datasets/{dataset_id}"
                    f"/submissions/{submit_id}/exports"
                )
                _post_multipart(
                    export_url,
                    {"format": export_format},
                    zip_bytes,
                    file_field="file",
                    filename=f"{export_format}.zip",
                )
                export_upload_status = "ok"
        except Exception as exc:
            export_upload_status = f"failed: {exc}"

    _base["export_upload_status"] = export_upload_status

    # ── 6. 歷史記錄 ───────────────────────────────────────────────────────────
    finished_at = datetime.now(timezone.utc).isoformat()
    _base["finished_at"] = finished_at

    if ok_count > 0 or failed_count > 0:
        if failed_count == 0:
            hist_status = "ok"
        elif ok_count == 0:
            hist_status = "fail"
        else:
            hist_status = "partial_fail"

        _cfg.append_sync_history(manifest_id, {
            "submit_id": submit_id,
            "dataset_id": dataset_id,
            "scope": scope,
            "scope_count": len(send_items),
            "ok_count": ok_count,
            "failed_count": failed_count,
            "formats": [export_format] if export_format != "none" else [],
            "export_upload_status": export_upload_status,
            "started_at": _base["started_at"],
            "finished_at": finished_at,
            "status": hist_status,
            **upload_meta,
        })

    # ── 7. 最終 mode ──────────────────────────────────────────────────────────
    if failed_count == 0:
        mode = "done"
    elif ok_count == 0:
        mode = "fail"
    else:
        mode = "partial_fail"

    return {**_base, "mode": mode, "error": None}
