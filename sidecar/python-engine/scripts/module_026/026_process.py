from __future__ import annotations

"""
module_026/026_process.py — 統一資料來源處理層。
支援三種模式：local（本地資料夾）、remote（遠端下載）、iwsc（iWISC 任務認領）。
"""

import importlib.util as _ilu
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

_HERE  = Path(__file__).resolve().parent
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CIM_LOG_DIR  = Path(os.environ.get("CIM_LOG_DIR", str(_PROJECT_ROOT / "tmp" / "cim_log")))

# ── 動態載入依賴 ──────────────────────────────────────────────────────────────

def _load(name: str, path: Path):
    spec = _ilu.spec_from_file_location(name, path)
    mod  = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_cfg  = _load("_026_config", _HERE / "_config.py")
_mdb  = _load("_manifest_db", _HERE.parent / "shared" / "_manifest_db.py")
_p010 = _load("_010_process", _HERE.parent / "module_010" / "010_process.py")


def _get_service():
    from plugins.labeling.domain.services import AnnotationService
    from plugins.labeling.domain.storage.workspace import AnnotationWorkspace
    ws_path = _cfg.get_annotation_workspace_path()
    return AnnotationService(AnnotationWorkspace(ws_path))


def _error(msg: str) -> dict:
    return {"mode": "error", "manifest_id": "", "total_count": 0, "items": [], "error": msg}


def _save_manifest(items: list[dict], name: str, source_type: str, source_cfg: dict) -> str:
    manifest_id = uuid4().hex
    db_path = _cfg.get_manifest_db_path()
    _mdb.create_manifest(db_path, manifest_id, name, source_type, source_cfg)
    if items:
        _mdb.add_manifest_items(db_path, manifest_id, items)
    return manifest_id


# ─── 各模式執行邏輯 ───────────────────────────────────────────────────────────

def _run_local(params: dict) -> dict:
    folder_path = params.get("folder_path", "").strip()
    if not folder_path:
        return _error("請提供資料夾路徑")
    if not Path(folder_path).exists():
        return _error(f"路徑不存在：{folder_path}")

    recursive  = bool(params.get("recursive", True))
    extensions = params.get("extensions", [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"])
    items      = _p010.scan_folder(folder_path, recursive, extensions)
    name       = params.get("manifest_name") or Path(folder_path).name or f"local_{datetime.now():%Y%m%d_%H%M%S}"

    manifest_id = _save_manifest(items, name, "folder",
                                  {"folder_path": folder_path, "recursive": recursive, "extensions": extensions})
    _cfg.write_shared({
        "last_manifest_id": manifest_id,
        "source_type": "local",
        "pending_reload": False,
    })
    return {"mode": "ready", "manifest_id": manifest_id, "manifest_name": name,
            "total_count": len(items), "items": items[:20], "error": None}


def _run_remote(params: dict) -> dict:
    service_url  = params.get("service_url", "").strip()
    dataset_id   = params.get("dataset_id", "").strip()
    dataset_name = params.get("dataset_name", "").strip()
    overwrite    = bool(params.get("overwrite", False))

    if not service_url or not dataset_id:
        return _error("請先選擇資料集")

    try:
        _proc19 = _load("_019_process", _HERE.parent / "module_019" / "019_process.py")
        _cfg19  = _load("_019_config",  _HERE.parent / "module_019" / "_config.py")

        downloads_dir = _cfg19.get_downloads_dir()
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in dataset_name) or dataset_id
        existing  = sorted(downloads_dir.glob(f"{safe_name}_*"), reverse=True)

        if existing and not overwrite:
            folder_path = str(existing[0])
        else:
            folder_path = _proc19.download_and_extract(service_url, dataset_id, dataset_name, downloads_dir)
    except Exception as exc:
        return _error(f"下載失敗：{exc}")

    extensions = [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"]
    items = _p010.scan_folder(folder_path, recursive=True, extensions=extensions)
    name  = dataset_name or f"remote_{datetime.now():%Y%m%d_%H%M%S}"

    manifest_id = _save_manifest(items, name, "remote",
                                  {"service_url": service_url, "dataset_id": dataset_id, "folder_path": folder_path})
    _cfg.write_shared({
        "last_manifest_id": manifest_id,
        "source_type": "remote",
        "pending_reload": False,
    })
    return {"mode": "ready", "manifest_id": manifest_id, "manifest_name": name,
            "total_count": len(items), "items": items[:20], "error": None}


def _run_iwsc(params: dict) -> dict:
    tenant_id = params.get("tenant_id", "").strip()
    ant_id    = params.get("ant_id", "").strip()
    user_id   = params.get("user_id", "").strip()

    if not tenant_id or not ant_id:
        return _error("請先在任務清單中選取一個待認領任務")
    if not user_id:
        return _error("請填入您的使用者 ID")

    try:
        service = _get_service()
        task    = service.claim_task(tenant_id, ant_id, user_id)
    except Exception as exc:
        return _error(f"認領失敗：{exc}")

    task_id    = task["task_id"]
    images_dir = service.workspace.task_images_dir(task_id)

    extensions = [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"]
    items = _p010.scan_folder(str(images_dir), recursive=False, extensions=extensions)

    name = f"iWISC-{ant_id}"
    manifest_id = _save_manifest(items, name, "iwsc",
                                  {"tenant_id": tenant_id, "task_id": task_id, "ant_id": ant_id})
    _cfg.write_shared({
        "last_manifest_id": manifest_id,
        "source_type": "iwsc",
        "iwsc_tenant_id": tenant_id,
        "iwsc_task_id": task_id,
        "iwsc_ant_id": ant_id,
        "pending_reload": False,
    })
    return {"mode": "ready", "manifest_id": manifest_id, "manifest_name": name,
            "total_count": len(items), "items": items[:20],
            "iwsc_task_id": task_id, "iwsc_ant_id": ant_id, "error": None}


# ─── 公開入口 ─────────────────────────────────────────────────────────────────

def execute_logic(params: dict) -> dict:
    mode = params.get("mode", "local")
    if mode == "local":
        return _run_local(params)
    elif mode == "remote":
        return _run_remote(params)
    elif mode == "iwsc":
        return _run_iwsc(params)
    return _error(f"未知的來源類型：{mode}")
