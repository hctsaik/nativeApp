from __future__ import annotations

"""
020_process.py — Upload Archive 核心邏輯
無 Streamlit import。

提供兩個公開函式：
  list_submissions(params)    → 查詢 Service 的上傳記錄
  execute_logic(params)       → 下載指定 submit_id 的 ZIP 並解壓
"""

import importlib.util as _ilu
import json
import os
import shutil
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_020_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_STREAM_CHUNK = 1024 * 1024  # 1 MB


# ─── HTTP 輔助 ────────────────────────────────────────────────────────────────

def _get_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body}") from e


def _download_stream(url: str, dest: Path, progress_cb=None, timeout: int = 120) -> int:
    """串流下載到 dest，回傳寫入 bytes。"""
    req = urllib.request.Request(url, method="GET")
    tmp = dest.with_suffix(".tmp")
    written = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            with tmp.open("wb") as f:
                while True:
                    chunk = resp.read(_STREAM_CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    written += len(chunk)
                    if progress_cb:
                        progress_cb(written)
        os.replace(tmp, dest)
        return written
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


# ─── 查詢 ─────────────────────────────────────────────────────────────────────

def list_submissions(params: dict) -> dict:
    """
    params:
        service_url:  str
        nt_account:   str
        system_name:  str
        data_type:    str   ("" = 不過濾)
        date_from:    str   (YYYY-MM-DD)
        date_to:      str   (YYYY-MM-DD)
        page:         int   (1-based)
        page_size:    int
    """
    service_url: str = params.get("service_url", "").rstrip("/")
    nt_account: str = params.get("nt_account", "")
    system_name: str = params.get("system_name", "")
    data_type: str = params.get("data_type", "")
    date_from: str = params.get("date_from", "")
    date_to: str = params.get("date_to", "")
    page: int = int(params.get("page", 1))
    page_size: int = int(params.get("page_size", _cfg.PAGE_SIZE))

    if not service_url:
        return {"mode": "error", "error": "未填寫 Service URL", "total": 0, "items": []}

    qs: dict[str, str] = {
        "page": str(page),
        "page_size": str(page_size),
    }
    if nt_account:
        qs["nt_account"] = nt_account
    if system_name:
        qs["system_name"] = system_name
    if data_type:
        qs["data_type"] = data_type
    if date_from:
        qs["date_from"] = date_from
    if date_to:
        qs["date_to"] = date_to

    url = f"{service_url}/api/v1/submissions?{urllib.parse.urlencode(qs)}"
    try:
        data = _get_json(url)
        return {
            "mode": "ok",
            "total": data.get("total", 0),
            "page": data.get("page", page),
            "page_size": data.get("page_size", page_size),
            "items": data.get("items", []),
            "error": None,
        }
    except Exception as exc:
        return {"mode": "error", "error": str(exc), "total": 0, "items": []}


# ─── 下載 ─────────────────────────────────────────────────────────────────────

def execute_logic(params: dict) -> dict:
    """
    params:
        service_url: str
        nt_account:  str
        submit_id:   str
    """
    service_url: str = params.get("service_url", "").rstrip("/")
    nt_account: str = params.get("nt_account", "")
    submit_id: str = params.get("submit_id", "")

    _base = {
        "submit_id": submit_id,
        "zip_path": "",
        "extract_dir": "",
        "size_bytes": 0,
    }

    if not service_url:
        return {**_base, "mode": "error", "error": "未填寫 Service URL"}
    if not submit_id:
        return {**_base, "mode": "error", "error": "未選擇要下載的批次"}

    qs = urllib.parse.urlencode({"nt_account": nt_account})
    url = f"{service_url}/api/v1/submissions/{submit_id}/download?{qs}"

    archive_dir = _cfg.get_archive_dir(submit_id)
    zip_path = archive_dir / f"{submit_id}.zip"

    try:
        size = _download_stream(url, zip_path)
        _base["size_bytes"] = size
        _base["zip_path"] = str(zip_path)
    except Exception as exc:
        return {**_base, "mode": "error", "error": f"下載失敗：{exc}"}

    # 解壓
    extract_dir = archive_dir
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
        _base["extract_dir"] = str(extract_dir)
    except Exception as exc:
        return {**_base, "mode": "warn",
                "error": f"ZIP 解壓失敗（原始 zip 保留）：{exc}",
                "zip_path": str(zip_path), "extract_dir": ""}

    return {**_base, "mode": "done", "error": None}
