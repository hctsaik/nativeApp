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

_LOG_DIR.mkdir(parents=True, exist_ok=True)
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

def _json_matches_image(json_file: Path, target: Path) -> bool:
    """Return True when a LabelMe JSON either omits imagePath or points at target."""
    try:
        stored = json.loads(json_file.read_text(encoding="utf-8")).get("imagePath", "")
        if not stored:
            return True
        stored_path = Path(stored)
        if not stored_path.is_absolute():
            stored_path = json_file.parent / stored_path
        return stored_path.resolve() == target
    except Exception:
        return True


def _find_annotation(img_path: str) -> str | None:
    """尋找與圖片對應的 LabelMe JSON 標注檔，回傳路徑或 None。

    module_012 僅使用影像同目錄同名 .json。
    """
    if not img_path:
        return None

    target = Path(img_path).resolve()

    same_dir = Path(img_path).with_suffix(".json")
    if same_dir.exists() and _json_matches_image(same_dir, target):
        return str(same_dir)

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


def get_labelme_exe() -> str:
    """回傳 LabelMe 執行檔路徑。"""
    env_exe = os.environ.get("LABELME_EXE", "")
    candidates = [
        Path(env_exe) if env_exe else None,
        _PROJECT_ROOT.parent / "LabelMe_Dino" / ".venv" / "Scripts" / "labelme.exe",
        _PROJECT_ROOT / "LabelMe_Dino" / ".venv" / "Scripts" / "labelme.exe",
    ]
    for c in candidates:
        if c and c.exists():
            return str(c)
    return "labelme"


# ─── 公開 API ─────────────────────────────────────────────────────────────────

def execute_logic(params: dict) -> dict:
    """
    掃描 manifest 的所有圖片，確認標注狀態，準備 X-AnyLabeling 設定檔。

    params:
        manifest_id: str
        annotation_tool: str
        labels: list[str]
    回傳:
        mode: 'ready' | 'error'
        manifest_id: str
        manifest_name: str
        labels: list[str]
        annotation_tool: str
        autorefresh_enabled: bool
        autorefresh_seconds: int
        xany_exe: str
        labelme_exe: str
        classes_path: str
        xany_work_dir: str
        total: int
        annotated: int
        items: list[dict]   # {item_id, file_path, width, height, has_ann, ann_path, shape_count}
        error: str | None
    """
    _log.info("=" * 60)
    _log.info("[012] execute_logic 開始")
    _log.info("[012] 收到 params: manifest_id=%s | labels=%s | classification_labels=%s",
              params.get("manifest_id", ""), params.get("labels", []),
              params.get("classification_labels", []))

    manifest_id: str = params.get("manifest_id", "")
    annotation_tool: str = params.get("annotation_tool", "x-anylabeling")
    if annotation_tool not in {"x-anylabeling", "labelme"}:
        annotation_tool = "x-anylabeling"
    labels: list[str] = params.get("labels", [])
    classification_labels: list[str] = params.get("classification_labels", [])
    autorefresh_enabled: bool = bool(params.get("autorefresh_enabled", True))
    autorefresh_seconds: int = int(params.get("autorefresh_seconds", 10) or 10)
    autorefresh_seconds = max(5, min(300, autorefresh_seconds))

    # ── 1. 驗證 manifest_id ────────────────────────────────────────────────────
    if not manifest_id:
        _log.error("[012] manifest_id 為空，返回 error")
        return {"mode": "error", "error": "未選擇 Manifest", "manifest_id": "",
                "manifest_name": "", "annotation_tool": annotation_tool, "labels": labels,
                "classification_labels": classification_labels,
                "xany_exe": "", "labelme_exe": "", "classes_path": "", "xany_work_dir": "",
                "total": 0, "annotated": 0, "items": []}

    # ── 2. 讀取 manifest 基本資訊 ──────────────────────────────────────────────
    db_path = _cfg.get_manifest_db_path()
    _log.info("[012] 查詢 DB: %s", db_path)
    manifest = _mdb.get_manifest(db_path, manifest_id)
    if manifest is None:
        _log.error("[012] 找不到 manifest_id=%s", manifest_id)
        return {"mode": "error", "error": f"找不到 Manifest：{manifest_id}",
                "manifest_id": manifest_id, "manifest_name": "",
                "annotation_tool": annotation_tool, "labels": labels,
                "classification_labels": classification_labels,
                "xany_exe": "", "labelme_exe": "", "classes_path": "", "xany_work_dir": "",
                "total": 0, "annotated": 0, "items": []}

    manifest_name = manifest.get("name", manifest_id)
    _log.info("[012] manifest 找到: name=%s source_type=%s",
              manifest_name, manifest.get("source_type", "?"))

    # ── 3. 讀取所有圖片項目 ────────────────────────────────────────────────────
    all_db_items = _mdb.get_manifest_items(db_path, manifest_id)
    _log.info("[012] manifest 圖片數: %d", len(all_db_items))
    if all_db_items:
        _log.debug("[012] 前 3 筆 file_path: %s",
                   [it.get("file_path", "") for it in all_db_items[:3]])

    same_dir_ann_count = sum(
        1
        for it in all_db_items
        if it.get("file_path", "") and Path(it.get("file_path", "")).with_suffix(".json").exists()
    )
    _log.info("[012] 影像同目錄標注檔數=%d", same_dir_ann_count)
    if same_dir_ann_count == 0:
        _log.warning("[012] 未找到影像同目錄 .json → 所有圖片將標示為「未標注」")

    # ── 5. 掃描各圖片的標注狀態 ────────────────────────────────────────────────
    items: list[dict] = []
    annotated = 0
    for it in all_db_items:
        fp = it.get("file_path", "")
        ann_path = _find_annotation(fp) if fp else None
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

    # ── 6. 準備 X-AnyLabeling labels / GUI state ──────────────────────────────
    classes_txt = _cfg.get_classes_path(manifest_id)
    if labels:
        classes_txt.parent.mkdir(parents=True, exist_ok=True)
        classes_txt.write_text("\n".join(labels), encoding="utf-8")
        _log.info("[012] classes.txt 寫入: %s  內容=%s", classes_txt, labels)
    else:
        _log.warning("[012] labels 為空，classes.txt 未寫入")
    xany_work_dir = _cfg.get_xany_work_dir(manifest_id)

    # ── 7. 儲存 config（last_manifest_id 供 module_013 讀取）────────────────────
    try:
        cfg = _cfg.load_config()
        cfg["annotation_tool"] = annotation_tool
        cfg["annotation_labels"] = labels
        cfg["classification_labels"] = classification_labels
        cfg["autorefresh_enabled"] = autorefresh_enabled
        cfg["autorefresh_seconds"] = autorefresh_seconds
        cfg["last_manifest_id"] = manifest_id
        _cfg.save_config(cfg)
        _log.info("[012] module_012.json 已儲存: last_manifest_id=%s", manifest_id)
    except Exception as exc:
        _log.error("[012] module_012.json 儲存失敗: %s", exc)

    xany_exe = get_xany_exe()
    labelme_exe = get_labelme_exe()
    _log.info("[012] xany_exe: %s  exists=%s", xany_exe, Path(xany_exe).exists())
    _log.info("[012] labelme_exe: %s  exists=%s", labelme_exe, Path(labelme_exe).exists())
    _log.info("[012] execute_logic 完成 ✔  total=%d annotated=%d",
              len(items), annotated)
    _log.info("=" * 60)

    return {
        "mode":                 "ready",
        "manifest_id":          manifest_id,
        "manifest_name":        manifest_name,
        "annotation_tool":      annotation_tool,
        "labels":               labels,
        "classification_labels": classification_labels,
        "autorefresh_enabled":   autorefresh_enabled,
        "autorefresh_seconds":   autorefresh_seconds,
        "xany_exe":             xany_exe,
        "labelme_exe":          labelme_exe,
        "classes_path":          str(classes_txt),
        "xany_work_dir":         str(xany_work_dir),
        "total":                len(items),
        "annotated":            annotated,
        "items":                items,
        "error":                None,
    }
