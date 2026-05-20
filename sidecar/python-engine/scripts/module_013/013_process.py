from __future__ import annotations

"""
013_process.py — Update 處理層。
無 Streamlit import。

操作 C：依分類標籤將圖片（及旁邊的同名 .json）複製到 export_dir/{分類名稱}/。
B 操作已移除——標注 JSON 由 X-AnyLabeling 直接存回影像同目錄，無需另行複製。
"""

import importlib.util as _ilu
import json
import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

# ─── Logger 設定 ──────────────────────────────────────────────────────────────

_LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", str(Path(__file__).resolve().parents[4] / "tmp" / "cim_log")))
_LOG_FILE = _LOG_DIR / "module_013_process.log"

_LOG_DIR.mkdir(parents=True, exist_ok=True)
_handler = logging.FileHandler(str(_LOG_FILE), encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
_log = logging.getLogger("module_013")
if not _log.handlers:
    _log.addHandler(_handler)
_log.setLevel(logging.DEBUG)

# ─── 動態載入 _config + _manifest_db ─────────────────────────────────────────

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_013_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_mdb_spec = _ilu.spec_from_file_location(
    "_manifest_db", _HERE.parent / "shared" / "_manifest_db.py"
)
_mdb = _ilu.module_from_spec(_mdb_spec)
_mdb_spec.loader.exec_module(_mdb)


# ─── 輔助函式 ─────────────────────────────────────────────────────────────────

_INVALID_CHARS = re.compile(r'[/\\:*?"<>|]')


def _safe_dirname(label: str) -> str:
    """將分類 label 轉成合法的目錄名稱（去掉非法字元）。"""
    cleaned = _INVALID_CHARS.sub("_", label).strip()
    return cleaned or "unknown"


def _count_shapes(ann_path: str) -> int:
    """計算標注檔中的 shape 數量。"""
    try:
        data = json.loads(Path(ann_path).read_text(encoding="utf-8"))
        return len(data.get("shapes", []))
    except Exception:
        return 0


def _infer_source_folder(manifest: dict, items: list[dict]) -> str:
    """
    推算原始圖片資料夾。
    1. 優先用 manifest 的 source_path 欄位。
    2. Fallback：取所有 items 的 file_path 的 common parent。
    """
    source_path = (manifest or {}).get("source_path", "")
    if not source_path:
        try:
            source_config = json.loads((manifest or {}).get("source_config", "{}"))
            source_path = source_config.get("folder_path", "") or source_config.get("source_path", "")
        except Exception:
            source_path = ""
    if source_path and Path(source_path).exists():
        p = Path(source_path)
        return str(p if p.is_dir() else p.parent)

    # Fallback：從 items 推算
    parents = []
    for it in items:
        fp = it.get("file_path", "")
        if fp:
            parents.append(str(Path(fp).parent))
    if not parents:
        return ""

    from collections import Counter
    most_common = Counter(parents).most_common(1)[0][0]
    return most_common


# ─── 公開 API ─────────────────────────────────────────────────────────────────

def execute_logic(params: dict) -> dict:
    """
    執行 Update 邏輯。

    params:
        manifest_id: str
        export_dir: str          # 整理輸出目錄（可為空，會用預設值）
        organize_images: bool    # C：依分類整理圖片（同時帶走標注 JSON）
        dry_run: bool            # True=只掃描不動檔案, False=實際執行

    回傳:
        mode: "preview" | "done" | "error"
        manifest_id, manifest_name, source_folder: str
        export_dir: str
        organize_images: bool
        dry_run: bool
        items: list[dict]
        summary: dict  — total, ann_count, c_organized, ann_exported, errors
        output_json_path: str
        error: str | None
    """
    _log.info("=" * 60)
    _log.info("[013] execute_logic 開始  dry_run=%s", params.get("dry_run", True))
    _log.info("[013] params: manifest_id=%s | export_dir=%r | organize_images=%s | dry_run=%s",
              params.get("manifest_id", ""),
              params.get("export_dir", ""),
              params.get("organize_images", True),
              params.get("dry_run", True))

    manifest_id: str  = params.get("manifest_id", "")
    export_dir: str   = params.get("export_dir", "")
    organize_images: bool = bool(params.get("organize_images", True))
    dry_run: bool     = bool(params.get("dry_run", True))

    _base_result = {
        "manifest_id": manifest_id,
        "manifest_name": "",
        "source_folder": "",
        "export_dir": export_dir,
        "organize_images": organize_images,
        "dry_run": dry_run,
        "items": [],
        "summary": {"total": 0, "ann_count": 0, "c_organized": 0, "ann_exported": 0, "errors": 0},
        "output_json_path": "",
        "error": None,
    }

    # ── 1. 驗證 manifest_id ────────────────────────────────────────────────────
    if not manifest_id:
        _log.error("[013] manifest_id 為空，返回 error")
        return {**_base_result, "mode": "error", "error": "未選擇 Manifest"}

    # ── 2. 讀取 manifest 基本資訊 ──────────────────────────────────────────────
    db_path = _cfg.get_manifest_db_path()
    manifest = _mdb.get_manifest(db_path, manifest_id)
    if manifest is None:
        _log.error("[013] 找不到 manifest_id=%s", manifest_id)
        return {**_base_result, "mode": "error", "error": f"找不到 Manifest：{manifest_id}"}

    manifest_name: str = manifest.get("name", manifest_id)
    _log.info("[013] manifest: name=%s", manifest_name)

    # ── 3. 讀取所有圖片項目 ────────────────────────────────────────────────────
    all_db_items = _mdb.get_manifest_items(db_path, manifest_id)
    _log.info("[013] 圖片數: %d", len(all_db_items))

    # ── 4. 讀取分類結果 ────────────────────────────────────────────────────────
    classifications_path = _cfg.get_classification_path(manifest_id)
    classifications: dict[str, str] = {}
    if classifications_path.exists():
        try:
            classifications = json.loads(classifications_path.read_text(encoding="utf-8"))
            _log.info("[013] 分類結果: %d 筆", len(classifications))
        except Exception as exc:
            _log.error("[013] 分類結果讀取失敗: %s", exc)
    else:
        _log.info("[013] 無分類結果")

    # ── 5. source_folder（顯示用）+ export_dir ─────────────────────────────────
    source_folder = _infer_source_folder(manifest, all_db_items)
    _log.info("[013] source_folder (顯示用): %r", source_folder)

    if export_dir and export_dir.strip():
        img_export_dir = export_dir.strip()
    else:
        img_export_dir = str(_cfg.get_default_export_dir(manifest_id))
    _log.info("[013] img_export_dir: %r", img_export_dir)

    # ── 6. 建立 items 清單 ─────────────────────────────────────────────────────
    items: list[dict] = []
    c_organized = 0
    ann_exported = 0
    errors = 0

    for it in all_db_items:
        fp       = it.get("file_path", "")
        item_id  = it.get("item_id", "")
        filename = Path(fp).name if fp else ""
        stem     = Path(fp).stem if fp else ""

        # 標注資訊：X-AnyLabeling 存在影像同目錄同名 .json
        ann_src_path = Path(fp).with_suffix(".json") if fp else None
        ann_src = str(ann_src_path) if (ann_src_path and ann_src_path.exists()) else ""
        has_annotation = bool(ann_src)
        shape_count = _count_shapes(ann_src) if has_annotation else 0

        # 分類資訊
        classification = classifications.get(item_id, "") or classifications.get(filename, "")

        # C：複製圖片（+ 旁邊的 .json）到 export_dir/{分類名稱}/
        if img_export_dir and classification and filename:
            safe_label     = _safe_dirname(classification)
            organized_dst  = str(Path(img_export_dir) / safe_label / filename)
            ann_export_dst = str(Path(img_export_dir) / safe_label / f"{stem}.json") if has_annotation else ""
            c_action = "copy"
        elif classification and not img_export_dir:
            organized_dst  = ""
            ann_export_dst = ""
            c_action = "skip"
        elif not classification:
            organized_dst  = ""
            ann_export_dst = ""
            c_action = "n/a"
        else:
            organized_dst  = ""
            ann_export_dst = ""
            c_action = "skip"

        status    = "pending"
        error_msg = ""

        # ── 實際執行（dry_run=False）────────────────────────────────────────────
        if not dry_run:
            if organize_images and c_action == "copy" and fp and organized_dst:
                # 複製圖片
                try:
                    src_path = Path(fp)
                    dst_path = Path(organized_dst)
                    if src_path.exists():
                        dst_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src_path, dst_path)
                        c_organized += 1
                        status = "ok"
                        _log.info("[013][C] ✅ img  %s → %s", fp, organized_dst)
                    else:
                        error_msg += f"[C] 來源不存在：{fp} "
                        errors += 1
                        status = "error"
                        _log.error("[013][C] ❌ 來源不存在: %s", fp)
                except Exception as e:
                    error_msg += f"[C] {e} "
                    errors += 1
                    status = "error"
                    _log.error("[013][C] ❌ img copy 失敗 %s → %s | err=%s", fp, organized_dst, e)

                # 複製標注 JSON（與圖片同目錄）
                if ann_src and ann_export_dst:
                    try:
                        ann_dst_path = Path(ann_export_dst)
                        ann_dst_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(ann_src, ann_dst_path)
                        ann_exported += 1
                        _log.info("[013][C] ✅ json %s → %s", ann_src, ann_export_dst)
                    except Exception as e:
                        error_msg += f"[C-json] {e} "
                        errors += 1
                        status = "error"
                        _log.error("[013][C] ❌ json copy 失敗 %s → %s | err=%s", ann_src, ann_export_dst, e)

            if status == "pending":
                status = "ok"

        items.append({
            "file_path":      fp,
            "filename":       filename,
            "classification": classification,
            "has_annotation": has_annotation,
            "shape_count":    shape_count,
            "annotation_src": ann_src,
            "ann_export_dst": ann_export_dst,
            "organized_dst":  organized_dst,
            "c_action":       c_action if organize_images else "n/a",
            "status":         status,
            "error_msg":      error_msg.strip(),
        })

    # ── 7. 統計摘要 ────────────────────────────────────────────────────────────
    total     = len(items)
    ann_count = sum(1 for it in items if it["has_annotation"])
    c_cnt     = sum(1 for it in items if it["c_action"] == "copy")
    c_skip    = sum(1 for it in items if it["c_action"] == "skip")
    c_na      = sum(1 for it in items if it["c_action"] == "n/a")

    _log.info("[013] total=%d has_annotation=%d", total, ann_count)
    _log.info("[013] C: copy=%d skip=%d n/a=%d", c_cnt, c_skip, c_na)
    if c_cnt == 0:
        _log.warning("[013] c_action=copy 為 0 → 無分類記錄或無 export_dir，確認按鈕將 disabled")
    if not dry_run:
        _log.info("[013] 執行結果: c_organized=%d ann_exported=%d errors=%d",
                  c_organized, ann_exported, errors)

    summary = {
        "total":        total,
        "ann_count":    ann_count,
        "c_organized":  c_organized,
        "ann_exported": ann_exported,
        "errors":       errors,
    }

    # ── 8. 寫入 output JSON（dry_run=False 才寫，存在 export_dir）───────────────
    output_json_path = ""
    if not dry_run:
        try:
            ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = Path(img_export_dir) if img_export_dir else _cfg.get_default_export_dir(manifest_id)
            out_dir.mkdir(parents=True, exist_ok=True)
            output_json_path = str(out_dir / f"update_result_{ts}.json")
            output_data = {
                "manifest_id":    manifest_id,
                "manifest_name":  manifest_name,
                "source_folder":  source_folder,
                "export_dir":     img_export_dir,
                "organize_images": organize_images,
                "summary":        summary,
                "items":          items,
            }
            Path(output_json_path).write_text(
                json.dumps(output_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            _log.info("[013] output JSON: %s", output_json_path)
        except Exception as e:
            output_json_path = f"[寫入失敗] {e}"
            _log.error("[013] output JSON 寫入失敗: %s", e)

    mode = "preview" if dry_run else "done"
    _log.info("[013] execute_logic 完成 ✔  mode=%s", mode)
    _log.info("=" * 60)

    return {
        "mode":           mode,
        "manifest_id":    manifest_id,
        "manifest_name":  manifest_name,
        "source_folder":  source_folder,
        "export_dir":     img_export_dir,
        "organize_images": organize_images,
        "dry_run":        dry_run,
        "items":          items,
        "summary":        summary,
        "output_json_path": output_json_path,
        "error":          None,
    }
