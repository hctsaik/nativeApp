from __future__ import annotations

"""
019_process.py — Data Downloader 核心邏輯（無 Streamlit import）

流程：
1. 呼叫 Service API，取得 zip 下載 URL
2. 下載 zip 到 tmp 資料夾（progress callback）
3. 解壓 zip，images/ + annotations/ 合併到目標 folder
4. 讀 manifest.json，統計標注狀態
5. 寫 shared.json（suggested_folder_path, pending_reload=True）
"""

import importlib.util as _ilu
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_019_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)


def _download_zip(url: str, dest: Path, progress_cb=None, timeout: int = 30) -> None:
    """串流下載 zip，每 1MB 回報一次進度。"""
    import requests
    with requests.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, total, dest.name)


def _extract_zip(zip_path: Path, target_dir: Path) -> dict:
    """
    解壓 zip，合併 images/ 和 annotations/ 到 target_dir 同一層。
    回傳 manifest_items（從 zip 內的 manifest.json 讀取）。
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest_items: list[dict] = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()

        # 讀 manifest.json
        manifest_names = [n for n in names if n.endswith("manifest.json") and "/" not in n.replace("manifest.json", "")]
        if manifest_names:
            with zf.open(manifest_names[0]) as mf:
                try:
                    data = json.loads(mf.read().decode("utf-8"))
                    manifest_items = data.get("items", [])
                except Exception:
                    manifest_items = []

        # 解壓 images/
        image_entries = [n for n in names if n.startswith("images/") and not n.endswith("/")]
        for entry in image_entries:
            file_name = Path(entry).name
            target_path = target_dir / file_name
            with zf.open(entry) as src, open(target_path, "wb") as dst:
                shutil.copyfileobj(src, dst)

        # 解壓 annotations/（.json 優先，若衝突記錄）
        annotation_entries = [n for n in names if n.startswith("annotations/") and n.endswith(".json")]
        conflicts: list[str] = []
        for entry in annotation_entries:
            file_name = Path(entry).name
            target_path = target_dir / file_name
            if target_path.exists():
                conflicts.append(file_name)
            with zf.open(entry) as src, open(target_path, "wb") as dst:
                shutil.copyfileobj(src, dst)

    return {"manifest_items": manifest_items, "conflicts": conflicts}


def _scan_annotation_status(target_dir: Path, manifest_items: list[dict]) -> list[dict]:
    """
    掃描每個 item 的標注狀態。
    status: "annotated" | "needs_review" | "empty"
    """
    results: list[dict] = []
    for item in manifest_items:
        file_name = item.get("file_name", "")
        stem = Path(file_name).stem
        ann_path = target_dir / f"{stem}.json"

        if ann_path.exists():
            try:
                data = json.loads(ann_path.read_text(encoding="utf-8"))
                shapes = data.get("shapes", [])
                flags = data.get("flags", {})
                has_content = bool(shapes) or bool(flags.get("classification"))
                status = "needs_review" if has_content else "empty"
            except Exception:
                status = "empty"
        else:
            status = "empty"

        results.append({
            "file_name": file_name,
            "status": status,
            "metadata": item.get("metadata", {}),
        })
    return results


def execute_logic(params: dict) -> dict:
    service_url: str = params.get("service_url", "").rstrip("/")
    dataset_id: str = params.get("dataset_id", "")
    dataset_name: str = params.get("dataset_name", "")
    overwrite: bool = bool(params.get("overwrite", False))

    _base = {
        "dataset_id": dataset_id,
        "dataset_name": dataset_name,
        "local_dir": "",
        "total": 0,
        "annotated": 0,
        "needs_review": 0,
        "empty": 0,
        "conflicts": [],
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }

    if not service_url:
        return {**_base, "mode": "error", "error": "未設定 Service URL"}
    if not dataset_id:
        return {**_base, "mode": "error", "error": "未選擇資料集"}

    # 目標資料夾：downloads/{dataset_name}_{timestamp}/
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in dataset_name) or dataset_id
    target_dir = _cfg.get_downloads_dir() / f"{safe_name}_{timestamp}"

    # 若已存在且不覆蓋，直接使用
    existing_dirs = sorted(_cfg.get_downloads_dir().glob(f"{safe_name}_*"), reverse=True)
    if existing_dirs and not overwrite:
        target_dir = existing_dirs[0]
        _cfg.write_progress(0, 0, "", "使用已有資料夾", running=False)
    else:
        # 下載 zip
        zip_url = f"{service_url}/datasets/{dataset_id}/download"
        _cfg.write_progress(0, 0, "", "下載中", running=True)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_zip = Path(tmp_dir) / "package.zip"
            try:
                def _dl_cb(done: int, total: int, name: str) -> None:
                    mb_done = done // (1024 * 1024)
                    mb_total = total // (1024 * 1024) if total else 0
                    label = f"{mb_done}MB / {mb_total}MB" if mb_total else f"{mb_done}MB"
                    _cfg.write_progress(done, total, label, "下載中", running=True)

                _download_zip(zip_url, tmp_zip, progress_cb=_dl_cb)
            except Exception as exc:
                _cfg.write_progress(0, 0, "", "下載失敗", running=False, error=str(exc))
                return {**_base, "mode": "error", "error": f"下載失敗：{exc}"}

            # 解壓到 tmp，成功後 rename 到 target_dir
            tmp_extract = Path(tmp_dir) / "extracted"
            _cfg.write_progress(0, 0, "", "解壓中", running=True)
            try:
                extract_result = _extract_zip(tmp_zip, tmp_extract)
            except Exception as exc:
                _cfg.write_progress(0, 0, "", "解壓失敗", running=False, error=str(exc))
                return {**_base, "mode": "error", "error": f"解壓失敗：{exc}"}

            # Atomic rename
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.move(str(tmp_extract), str(target_dir))

    # 掃描標注狀態
    _cfg.write_progress(0, 0, "", "掃描標注狀態", running=True)
    manifest_items = extract_result.get("manifest_items", []) if "extract_result" in dir() else []
    if not manifest_items:
        # fallback：掃描 target_dir 內所有圖片
        image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"}
        manifest_items = [
            {"file_name": f.name, "metadata": {}}
            for f in sorted(target_dir.iterdir())
            if f.suffix.lower() in image_exts
        ]

    item_statuses = _scan_annotation_status(target_dir, manifest_items)
    annotated = sum(1 for i in item_statuses if i["status"] == "annotated")
    needs_review = sum(1 for i in item_statuses if i["status"] == "needs_review")
    empty = sum(1 for i in item_statuses if i["status"] == "empty")

    # 寫 shared.json
    _cfg.write_shared_fields({
        "suggested_folder_path": str(target_dir),
        "pending_reload": True,
    })

    _cfg.write_progress(len(item_statuses), len(item_statuses), "", "完成", running=False)

    return {
        **_base,
        "mode": "done",
        "error": None,
        "local_dir": str(target_dir),
        "total": len(item_statuses),
        "annotated": annotated,
        "needs_review": needs_review,
        "empty": empty,
        "conflicts": extract_result.get("conflicts", []) if "extract_result" in dir() else [],
        "item_statuses": item_statuses,
    }


def list_datasets(service_url: str) -> list[dict]:
    """列出 Service 上的資料集。"""
    import requests
    try:
        resp = requests.get(f"{service_url.rstrip('/')}/datasets", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        raise RuntimeError(f"無法取得資料集清單：{exc}") from exc
