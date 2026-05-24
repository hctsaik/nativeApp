from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import streamlit as st

# ─── 動態載入 _config ─────────────────────────────────────────────────────────

import importlib.util as _ilu

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_010_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_help_spec = _ilu.spec_from_file_location("_help", _HERE.parent / "shared" / "_help.py")
_help = _ilu.module_from_spec(_help_spec)
_help_spec.loader.exec_module(_help)

# ─── 預設副檔名選項 ────────────────────────────────────────────────────────────

_DEFAULT_EXTENSIONS = [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"]


# ─── 主入口 ──────────────────────────────────────────────────────────────────

def render_input() -> dict:
    _help.render_help_header(
        "module_010",
        "input",
        "📦 Data Feeder — 資料來源設定",
        "從資料夾、資料庫或 API 建立標準化圖片清單（DatasetManifest）",
    )

    cfg = _cfg.load_config()

    # ── 來源類型 Radio ─────────────────────────────────────────────────────────
    _source_options = ["📁 資料夾", "🗄️ 資料庫", "🌐 API"]
    _source_type_map = {"📁 資料夾": "folder", "🗄️ 資料庫": "db", "🌐 API": "api"}
    _source_label_map = {"folder": "📁 資料夾", "db": "🗄️ 資料庫", "api": "🌐 API"}

    default_source_label = _source_label_map.get(cfg.get("last_source_type", "folder"), "📁 資料夾")
    source_label = st.radio(
        "資料來源類型",
        _source_options,
        index=_source_options.index(default_source_label),
        horizontal=True,
        key="m010_source_type",
    )
    source_type = _source_type_map[source_label]

    params: dict = {}

    if source_type == "folder":
        if "_folder_chosen" in st.session_state:
            st.session_state["m010_folder_path"] = st.session_state.pop("_folder_chosen")
        if "m010_folder_path" not in st.session_state:
            # 若 module_019 已下載並寫入 suggested_folder_path，自動填入
            suggested = _cfg.read_shared_suggested_folder()
            st.session_state["m010_folder_path"] = suggested or cfg.get("last_folder_path", "")

        if _cfg.read_shared_suggested_folder() and not st.session_state.get("_m010_suggested_banner_dismissed"):
            st.info(
                "📥 **Data Downloader** 已下載新資料集，路徑已自動填入。"
                " 確認後請按「執行」載入。",
                icon="ℹ️",
            )

        path_col, btn_col = st.columns([5, 1])
        with path_col:
            folder_path = st.text_input(
                "資料夾路徑",
                key="m010_folder_path",
                placeholder="C:/path/to/images",
            )
        with btn_col:
            st.markdown("<div style='margin-top:28px'>", unsafe_allow_html=True)
            if st.button("📂 瀏覽", use_container_width=True, key="m010_browse_btn"):
                try:
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-c",
                            (
                                "import tkinter as tk; from tkinter import filedialog; "
                                "root=tk.Tk(); root.withdraw(); root.wm_attributes('-topmost',True); "
                                "p=filedialog.askdirectory(title='選擇圖片資料夾'); "
                                "root.destroy(); print(p or '',end='')"
                            ),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    chosen = result.stdout.strip()
                    if chosen:
                        st.session_state["_folder_chosen"] = chosen
                        st.rerun()
                except Exception as e:
                    st.warning(f"無法開啟資料夾選擇器：{e}\n請直接在上方文字框貼上路徑。")
            st.markdown("</div>", unsafe_allow_html=True)

        if "m010_recursive" not in st.session_state:
            st.session_state["m010_recursive"] = cfg.get("recursive_scan", True)
        recursive = st.checkbox("遞迴掃描子資料夾", key="m010_recursive")

        if "m010_extensions" not in st.session_state:
            st.session_state["m010_extensions"] = cfg.get("image_extensions", _DEFAULT_EXTENSIONS)
        selected_exts = st.multiselect(
            "允許的圖片副檔名",
            options=_DEFAULT_EXTENSIONS,
            key="m010_extensions",
        )

        params = {
            "source_type": "folder",
            "folder_path": folder_path,
            "recursive": recursive,
            "extensions": selected_exts or _DEFAULT_EXTENSIONS,
        }

    elif source_type == "db":
        db_path_val = st.text_input(
            "SQLite 資料庫路徑",
            key="m010_db_path",
            placeholder="C:/path/to/database.sqlite",
        )
        db_sql_val = st.text_area(
            "SQL 查詢",
            key="m010_db_sql",
            placeholder="SELECT file_path FROM images WHERE ...",
            help="查詢結果必須包含 file_path 欄位",
            height=120,
        )
        params = {"source_type": "db", "db_path": db_path_val, "db_sql": db_sql_val}

    else:  # api
        api_url_val = st.text_input(
            "API URL",
            key="m010_api_url",
            placeholder="https://api.example.com/images",
        )
        api_method_val = st.radio("HTTP 方法", ["GET", "POST"], horizontal=True, key="m010_api_method")
        api_headers_val = st.text_area(
            "請求標頭（JSON 格式）",
            key="m010_api_headers",
            placeholder='{"Authorization": "Bearer <token>"}',
            value=st.session_state.get("m010_api_headers", "{}"),
            height=80,
        )
        api_response_path_val = st.text_input(
            "回應資料路徑（dot-notation）",
            key="m010_api_response_path",
            placeholder="data.images",
            help="從 JSON 回應中取出圖片 URL 清單的路徑，例如 data.images",
        )
        params = {
            "source_type": "api",
            "api_url": api_url_val,
            "api_method": api_method_val,
            "api_headers": api_headers_val,
            "api_response_path": api_response_path_val,
        }

    if source_type == "folder":
        _p = params.get("folder_path", "").strip()
        params["manifest_name"] = Path(_p).name if _p else ""
    elif source_type == "db":
        _p = params.get("db_path", "").strip()
        params["manifest_name"] = Path(_p).stem if _p else ""
    else:  # api
        from urllib.parse import urlparse as _urlparse
        _u = params.get("api_url", "").strip()
        params["manifest_name"] = _urlparse(_u).hostname or "" if _u else ""

    return params
