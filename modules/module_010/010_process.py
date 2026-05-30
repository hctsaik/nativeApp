from __future__ import annotations

"""
module_010/010_process.py — Data Feeder 處理層。
無 Streamlit import。
"""

import hashlib
import importlib.util as _ilu
import json
import os
import sqlite3
import urllib.request
from datetime import datetime
from pathlib import Path
from uuid import uuid4

# ─── 路徑常數 ─────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parents[6]  # nativeApp
_CIM_LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", str(_PROJECT_ROOT / "tmp" / "cim_log")))

# ─── 動態載入 _manifest_db ────────────────────────────────────────────────────

_HERE = Path(__file__).resolve().parent
_spec = _ilu.spec_from_file_location(
    "_manifest_db", _HERE.parents[3] / "scripts" / "shared" / "_manifest_db.py"
)
_mdb = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mdb)

# ─── 動態載入 _config ─────────────────────────────────────────────────────────

_cfg_spec = _ilu.spec_from_file_location("_010_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)


# ─── 內部輔助 ─────────────────────────────────────────────────────────────────

def _md5_prefix(file_path: str, length: int = 16) -> str | None:
    """計算檔案 MD5，回傳前 length 個字元，失敗回傳 None。"""
    try:
        h = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:length]
    except Exception:
        return None


def _image_size(file_path: str) -> tuple[int | None, int | None]:
    """用 PIL 取得圖片尺寸，失敗回傳 (None, None)。"""
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            return img.width, img.height
    except Exception:
        return None, None


def _resolve_dot_path(data: object, dot_path: str) -> object:
    """
    依 dot-notation 路徑（如 "data.images"）取出巢狀值。
    若任一層不存在則回傳 None。
    """
    if not dot_path:
        return data
    for key in dot_path.split("."):
        if isinstance(data, dict):
            data = data.get(key)
        elif isinstance(data, (list, tuple)):
            try:
                data = data[int(key)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if data is None:
            return None
    return data


# ─── 公開 API ─────────────────────────────────────────────────────────────────

def scan_folder(
    folder_path: str,
    recursive: bool,
    extensions: list[str],
) -> list[dict]:
    """
    掃描資料夾，每個符合副檔名的圖片建立 item dict。
    回傳：
        [{"item_id": uuid4().hex, "file_path": str, "width": int|None,
          "height": int|None, "file_hash": str|None, "metadata": {}}, ...]
    """
    root = Path(folder_path)
    if not root.exists() or not root.is_dir():
        return []

    ext_set = {e.lower() for e in extensions}
    items: list[dict] = []

    if recursive:
        all_files = root.rglob("*")
    else:
        all_files = root.iterdir()

    for fp in sorted(all_files):
        if not fp.is_file():
            continue
        if fp.suffix.lower() not in ext_set:
            continue
        abs_path = str(fp.resolve())
        w, h = _image_size(abs_path)
        items.append(
            {
                "item_id": uuid4().hex,
                "file_path": abs_path,
                "width": w,
                "height": h,
                "file_hash": _md5_prefix(abs_path),
                "metadata": {},
            }
        )

    return items


def query_db_for_images(db_path_str: str, sql: str) -> list[dict]:
    """
    對指定 SQLite 資料庫執行 SQL，期望結果含 file_path 欄位。
    每筆轉成 item dict（item_id=新 UUID）。
    """
    try:
        conn = sqlite3.connect(db_path_str)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql).fetchall()
        conn.close()
    except Exception as exc:
        raise RuntimeError(f"資料庫查詢失敗：{exc}") from exc

    items: list[dict] = []
    for row in rows:
        row_dict = dict(row)
        fp = row_dict.get("file_path", "")
        if not fp:
            continue
        abs_path = str(Path(fp).resolve()) if fp else fp
        w, h = _image_size(abs_path)
        items.append(
            {
                "item_id": uuid4().hex,
                "file_path": abs_path,
                "width": w,
                "height": h,
                "file_hash": _md5_prefix(abs_path) if Path(abs_path).exists() else None,
                "metadata": {k: v for k, v in row_dict.items() if k != "file_path"},
            }
        )

    return items


def fetch_api_images(
    url: str,
    method: str,
    headers: dict,
    response_path: str,
) -> list[dict]:
    """
    呼叫 HTTP API（用 urllib.request，不依賴第三方）。
    response_path 是 dot-notation，如 "data.images"。
    假設最終值是 URL 字串清單。
    """
    req = urllib.request.Request(url, method=method.upper())
    for k, v in headers.items():
        req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except Exception as exc:
        raise RuntimeError(f"API 請求失敗：{exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"API 回應非合法 JSON：{exc}") from exc

    image_list = _resolve_dot_path(data, response_path)
    if image_list is None:
        raise RuntimeError(f"找不到 response_path '{response_path}' 對應的資料")
    if not isinstance(image_list, list):
        raise RuntimeError(f"response_path '{response_path}' 對應值不是 list")

    items: list[dict] = []
    for entry in image_list:
        if isinstance(entry, str):
            url_str = entry
        elif isinstance(entry, dict):
            url_str = entry.get("url", "") or entry.get("path", "") or str(entry)
        else:
            url_str = str(entry)
        items.append(
            {
                "item_id": uuid4().hex,
                "file_path": url_str,
                "width": None,
                "height": None,
                "file_hash": None,
                "metadata": {},
            }
        )

    return items


def execute_logic(params: dict) -> dict:
    """
    核心執行邏輯。

    params:
        source_type: 'folder'|'db'|'api'
        manifest_name: str
        # folder:
        folder_path: str
        recursive: bool
        extensions: list[str]
        # db:
        db_path: str
        db_sql: str
        # api:
        api_url: str
        api_method: str ('GET'|'POST')
        api_headers: str (JSON 字串)
        api_response_path: str

    回傳:
        mode: 'ready'|'error'|'idle'
        manifest_id: str
        manifest_name: str
        source_type: str
        total_count: int
        items: list[dict]  # 前 20 筆供預覽
        error: str|None
    """
    source_type: str = params.get("source_type", "folder")
    manifest_name: str = params.get("manifest_name", "").strip()

    if not manifest_name:
        manifest_name = f"manifest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 1. 依 source_type 掃描圖片
    try:
        if source_type == "folder":
            folder_path = params.get("folder_path", "")
            if not folder_path:
                return {
                    "mode": "error",
                    "manifest_id": "",
                    "manifest_name": manifest_name,
                    "source_type": source_type,
                    "total_count": 0,
                    "items": [],
                    "error": "請提供資料夾路徑",
                }
            if not Path(folder_path).exists():
                return {
                    "mode": "error",
                    "manifest_id": "",
                    "manifest_name": manifest_name,
                    "source_type": source_type,
                    "total_count": 0,
                    "items": [],
                    "error": f"路徑不存在：{folder_path}",
                }
            recursive = bool(params.get("recursive", True))
            extensions = params.get("extensions", [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"])
            all_items = scan_folder(folder_path, recursive, extensions)
            source_config = {
                "folder_path": folder_path,
                "recursive": recursive,
                "extensions": extensions,
            }

        elif source_type == "db":
            db_path_str = params.get("db_path", "")
            db_sql = params.get("db_sql", "")
            if not db_path_str or not db_sql:
                return {
                    "mode": "error",
                    "manifest_id": "",
                    "manifest_name": manifest_name,
                    "source_type": source_type,
                    "total_count": 0,
                    "items": [],
                    "error": "請提供 SQLite 路徑與 SQL 查詢",
                }
            all_items = query_db_for_images(db_path_str, db_sql)
            source_config = {"db_path": db_path_str, "sql": db_sql}

        elif source_type == "api":
            api_url = params.get("api_url", "")
            api_method = params.get("api_method", "GET")
            api_headers_str = params.get("api_headers", "{}")
            api_response_path = params.get("api_response_path", "")
            if not api_url:
                return {
                    "mode": "error",
                    "manifest_id": "",
                    "manifest_name": manifest_name,
                    "source_type": source_type,
                    "total_count": 0,
                    "items": [],
                    "error": "請提供 API URL",
                }
            try:
                api_headers = json.loads(api_headers_str) if api_headers_str.strip() else {}
            except json.JSONDecodeError:
                return {
                    "mode": "error",
                    "manifest_id": "",
                    "manifest_name": manifest_name,
                    "source_type": source_type,
                    "total_count": 0,
                    "items": [],
                    "error": "API Headers 必須是合法 JSON 格式",
                }
            all_items = fetch_api_images(api_url, api_method, api_headers, api_response_path)
            source_config = {
                "url": api_url,
                "method": api_method,
                "response_path": api_response_path,
            }

        else:
            return {
                "mode": "error",
                "manifest_id": "",
                "manifest_name": manifest_name,
                "source_type": source_type,
                "total_count": 0,
                "items": [],
                "error": f"不支援的 source_type：{source_type}",
            }

    except Exception as exc:
        return {
            "mode": "error",
            "manifest_id": "",
            "manifest_name": manifest_name,
            "source_type": source_type,
            "total_count": 0,
            "items": [],
            "error": str(exc),
        }

    # 2. 存入 DB
    manifest_id = uuid4().hex
    db_path = _cfg.get_manifest_db_path()

    try:
        _mdb.create_manifest(db_path, manifest_id, manifest_name, source_type, source_config)
        if all_items:
            _mdb.add_manifest_items(db_path, manifest_id, all_items)
    except Exception as exc:
        return {
            "mode": "error",
            "manifest_id": manifest_id,
            "manifest_name": manifest_name,
            "source_type": source_type,
            "total_count": len(all_items),
            "items": all_items[:20],
            "error": f"資料庫寫入失敗：{exc}",
        }

    # 3. 寫入 shared.json 供 module_012 自動銜接
    try:
        _cfg.write_shared_manifest_id(manifest_id)
    except Exception:
        pass

    return {
        "mode": "ready",
        "manifest_id": manifest_id,
        "manifest_name": manifest_name,
        "source_type": source_type,
        "total_count": len(all_items),
        "items": all_items[:20],
        "skip_preview": bool(params.get("skip_preview", False)),
        "error": None,
    }
