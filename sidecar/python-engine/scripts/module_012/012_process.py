from __future__ import annotations

"""
012_process.py — Annotation Session 處理層。
無 Streamlit import。
"""

import importlib.util as _ilu
import json
import logging
import os
from pathlib import Path

# ─── Logger 設定 ──────────────────────────────────────────────────────────────

_LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", str(Path(__file__).resolve().parents[4] / "tmp" / "cim_log")))
_LOG_FILE = _LOG_DIR / "module_012_process.log"

_handler = logging.FileHandler(str(_LOG_FILE), encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
_log = logging.getLogger("module_012")
if not _log.handlers:
    _log.addHandler(_handler)
_log.setLevel(logging.DEBUG)

# ─── 動態載入 _config + _manifest_db ─────────────────────────────────────────

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_012_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_mdb_spec = _ilu.spec_from_file_location(
    "_manifest_db", _HERE.parent / "shared" / "_manifest_db.py"
)
_mdb = _ilu.module_from_spec(_mdb_spec)
_mdb_spec.loader.exec_module(_mdb)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]


# ─── 輔助函式 ─────────────────────────────────────────────────────────────────

def _find_annotation(img_path: str, workspace_dir: str = "") -> str | None:
    """尋找與圖片對應的 LabelMe JSON 標注檔，回傳路徑或 None。

    先以 basename 快速命中，再用 JSON 內的 imagePath 欄位驗證圖片路徑是否吻合，
    以應對不同目錄下出現相同檔名（如 frame_000000.jpg）的情況。
    """
    if not workspace_dir:
        return None
    ann_dir = Path(workspace_dir) / "annotations"
    if not ann_dir.exists():
        return None

    target = Path(img_path).resolve()

    def _match(json_file: Path) -> bool:
        """回傳 True 若 JSON 的 imagePath 解析後與 target 相同。"""
        try:
            stored = json.loads(json_file.read_text(encoding="utf-8")).get("imagePath", "")
            if not stored:
                return True  # 無 imagePath 欄位則接受（向後相容）
            return (json_file.parent / stored).resolve() == target
        except Exception:
            return True

    # 快速路徑：basename 相符且 imagePath 吻合
    naive = ann_dir / Path(img_path).with_suffix(".json").name
    if naive.exists() and _match(naive):
        return str(naive)

    # 全掃：其他 JSON 檔是否有 imagePath 指向 target
    for jf in ann_dir.glob("*.json"):
        if jf == naive:
            continue
        try:
            stored = json.loads(jf.read_text(encoding="utf-8")).get("imagePath", "")
            if stored and (jf.parent / stored).resolve() == target:
                return str(jf)
        except Exception:
            continue

    return None


def _count_shapes(ann_path: str) -> int:
    """計算標注檔中的 shape 數量。"""
    try:
        data = json.loads(Path(ann_path).read_text(encoding="utf-8"))
        return len(data.get("shapes", []))
    except Exception:
        return 0


def get_xany_exe() -> str:
    """回傳 X-AnyLabeling 執行檔路徑。"""
    candidates = [
        _PROJECT_ROOT / ".venv-xanylabeling" / "Scripts" / "xanylabeling.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return "xanylabeling"


# ─── 公開 API ─────────────────────────────────────────────────────────────────

def execute_logic(params: dict) -> dict:
    """
    掃描 manifest 的所有圖片，確認標注狀態，準備 workspace。

    params:
        manifest_id: str
        labels: list[str]
        workspace_dir: str

    回傳:
        mode: 'ready' | 'error'
        manifest_id: str
        manifest_name: str
        labels: list[str]
        workspace_dir: str
        xany_exe: str
        total: int
        annotated: int
        items: list[dict]   # {item_id, file_path, width, height, has_ann, ann_path, shape_count}
        error: str | None
    """
    _log.info("=" * 60)
    _log.info("[012] execute_logic 開始")
    _log.info("[012] 收到 params: manifest_id=%s | labels=%s | classification_labels=%s | workspace_dir=%r",
              params.get("manifest_id", ""), params.get("labels", []),
              params.get("classification_labels", []), params.get("workspace_dir", ""))

    manifest_id: str = params.get("manifest_id", "")
    labels: list[str] = params.get("labels", [])
    classification_labels: list[str] = params.get("classification_labels", [])
    workspace_dir: str = params.get("workspace_dir", "")

    # ── 1. 驗證 manifest_id ────────────────────────────────────────────────────
    if not manifest_id:
        _log.error("[012] manifest_id 為空，返回 error")
        return {"mode": "error", "error": "未選擇 Manifest", "manifest_id": "",
                "manifest_name": "", "labels": labels,
                "classification_labels": classification_labels,
                "workspace_dir": workspace_dir,
                "xany_exe": "", "total": 0, "annotated": 0, "items": []}

    # ── 2. 讀取 manifest 基本資訊 ──────────────────────────────────────────────
    db_path = _cfg.get_manifest_db_path()
    _log.info("[012] 查詢 DB: %s", db_path)
    manifest = _mdb.get_manifest(db_path, manifest_id)
    if manifest is None:
        _log.error("[012] 找不到 manifest_id=%s", manifest_id)
        return {"mode": "error", "error": f"找不到 Manifest：{manifest_id}",
                "manifest_id": manifest_id, "manifest_name": "",
                "labels": labels, "classification_labels": classification_labels,
                "workspace_dir": workspace_dir,
                "xany_exe": "", "total": 0, "annotated": 0, "items": []}

    manifest_name = manifest.get("name", manifest_id)
    _log.info("[012] manifest 找到: name=%s source_type=%s",
              manifest_name, manifest.get("source_type", "?"))

    # ── 3. 讀取所有圖片項目 ────────────────────────────────────────────────────
    all_db_items = _mdb.get_manifest_items(db_path, manifest_id)
    _log.info("[012] manifest 圖片數: %d", len(all_db_items))
    if all_db_items:
        _log.debug("[012] 前 3 筆 file_path: %s",
                   [it.get("file_path", "") for it in all_db_items[:3]])

    # ── 4. 確定 workspace 路徑 ─────────────────────────────────────────────────
    ws_for_scan = workspace_dir if workspace_dir else str(_cfg.get_workspace_dir(manifest_id))
    _log.info("[012] workspace 路徑: %s  (來源: %s)",
              ws_for_scan, "params" if workspace_dir else "manifest_id 推算")

    ann_dir = Path(ws_for_scan) / "annotations"
    ann_dir_exists = ann_dir.exists()
    existing_anns = sorted(ann_dir.glob("*.json")) if ann_dir_exists else []
    _log.info("[012] annotations/ 目錄: exists=%s | 檔案數=%d",
              ann_dir_exists, len(existing_anns))
    if existing_anns:
        _log.info("[012] 已有標注檔: %s", [f.name for f in existing_anns])
    else:
        _log.warning("[012] annotations/ 目錄為空或不存在 → 所有圖片將標示為「未標注」")

    # ── 5. 掃描各圖片的標注狀態 ────────────────────────────────────────────────
    items: list[dict] = []
    annotated = 0
    for it in all_db_items:
        fp = it.get("file_path", "")
        ann_path = _find_annotation(fp, ws_for_scan) if fp else None
        has_ann = ann_path is not None
        sc = _count_shapes(ann_path) if has_ann else 0
        if has_ann:
            annotated += 1
            _log.debug("[012] ✅ %s → shapes=%d ann=%s",
                       Path(fp).name, sc, ann_path)
        items.append({
            "item_id":     it.get("item_id", ""),
            "file_path":   fp,
            "width":       it.get("width"),
            "height":      it.get("height"),
            "has_ann":     has_ann,
            "ann_path":    ann_path or "",
            "shape_count": sc,
        })

    _log.info("[012] 標注掃描完成: total=%d annotated=%d unannotated=%d",
              len(items), annotated, len(items) - annotated)

    # ── 6. 準備 workspace ──────────────────────────────────────────────────────
    ws = Path(workspace_dir) if workspace_dir else _cfg.get_workspace_dir(manifest_id)
    ws.mkdir(parents=True, exist_ok=True)
    classes_txt = ws / "classes.txt"
    if labels:
        classes_txt.write_text("\n".join(labels), encoding="utf-8")
        _log.info("[012] classes.txt 寫入: %s  內容=%s", classes_txt, labels)
    else:
        _log.warning("[012] labels 為空，classes.txt 未寫入")

    # ── 7. 儲存 config（last_manifest_id 供 module_013 讀取）────────────────────
    try:
        cfg = _cfg.load_config()
        cfg["annotation_labels"] = labels
        cfg["classification_labels"] = classification_labels
        cfg["last_manifest_id"] = manifest_id
        _cfg.save_config(cfg)
        _log.info("[012] module_012.json 已儲存: last_manifest_id=%s", manifest_id)
    except Exception as exc:
        _log.error("[012] module_012.json 儲存失敗: %s", exc)

    xany_exe = get_xany_exe()
    _log.info("[012] xany_exe: %s  exists=%s", xany_exe, Path(xany_exe).exists())
    _log.info("[012] execute_logic 完成 ✔  total=%d annotated=%d workspace=%s",
              len(items), annotated, str(ws))
    _log.info("=" * 60)

    return {
        "mode":                 "ready",
        "manifest_id":          manifest_id,
        "manifest_name":        manifest_name,
        "labels":               labels,
        "classification_labels": classification_labels,
        "workspace_dir":        str(ws),
        "xany_exe":             xany_exe,
        "total":                len(items),
        "annotated":            annotated,
        "items":                items,
        "error":                None,
    }
