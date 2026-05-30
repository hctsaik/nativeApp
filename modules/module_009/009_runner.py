"""
module_009 — 統一標注平台
Single-page Streamlit UI (no Input/Output split).
"""
from __future__ import annotations

import importlib.util as _ilu
import json
import os
import subprocess
import sys
from pathlib import Path

import streamlit as st
from streamlit_autorefresh import st_autorefresh

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

_spec = _ilu.spec_from_file_location("_009_process", _HERE / "009_process.py")
_proc = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_proc)

from _config import get_annotation_labels, get_db_path, load_config
from _db import get_frame_annotations

_STATUS_BADGE = {
    "未標記": "⬜",
    "追蹤中": "⏳",
    "標記中": "🟡",
    "已標記": "🟢",
    "已同步": "🔵",
}

_STATUS_ORDER = ["未標記", "追蹤中", "標記中", "已標記", "已同步"]


# ── Helper functions ───────────────────────────────────────────────────────────

def _start_annotation_flow(session_id: int, asset: dict) -> None:
    labels = get_annotation_labels()
    cfg = load_config()
    anchor_info = {
        "anchor_frame_idx": (asset.get("total_frames") or 1) // 2,
        "anchor_bboxes": [],
        "before_sec": cfg.get("default_before_sec", 1.0),
        "after_sec": cfg.get("default_after_sec", 1.0),
        "labels": labels,
    }
    result = _proc.start_annotation(session_id, anchor_info)
    if result.get("ok"):
        if result.get("asset_type") == "image_dir":
            st.success("圖片已準備好，即將開啟 X-AnyLabeling...")
        else:
            st.success("追蹤 job 已啟動，請稍候...")
    else:
        st.error(f"啟動失敗：{result.get('error')}")
    st.rerun()


def _render_action_button(session_id: int, status: str, asset: dict, row_idx: int) -> None:
    key = f"action_{session_id}_{row_idx}"
    if status == "未標記":
        if st.button("🛠️ 開啟標注", key=key, use_container_width=True):
            _start_annotation_flow(session_id, asset)
    elif status == "追蹤中":
        st.button("⏳ 追蹤中...", key=key, disabled=True, use_container_width=True)
    elif status == "標記中":
        st.button("🔒 標注中", key=key, disabled=True, use_container_width=True)
    elif status in ("已標記", "已同步"):
        if st.button("🔍 修正", key=key, use_container_width=True):
            current = st.session_state.get("expanded_session")
            st.session_state["expanded_session"] = None if current == session_id else session_id
            st.rerun()
    else:
        st.button("—", key=key, disabled=True, use_container_width=True)


def _render_correction_panel(session_id: int, asset: dict) -> None:
    frame_rows = get_frame_annotations(get_db_path(), session_id)
    if not frame_rows:
        st.info("無已標注幀可供修正。")
        return

    st.markdown("**🔍 選擇要修正的幀：**")
    session = _proc.get_session_status(session_id)
    xany_dir = Path(session["xany_project_dir"]) if (session and session.get("xany_project_dir")) else None

    max_thumbs = 8
    thumb_rows = frame_rows[:max_thumbs]
    thumb_cols = st.columns(len(thumb_rows))
    for ci, row in enumerate(thumb_rows):
        fidx = row["frame_idx"]
        with thumb_cols[ci]:
            if xany_dir:
                frame_path = xany_dir / "frames" / f"frame_{fidx:06d}.jpg"
                if frame_path.exists():
                    st.image(str(frame_path), caption=f"#{fidx}", use_container_width=True)
            if st.button(f"修正 #{fidx}", key=f"fix_{session_id}_{fidx}"):
                result = _proc.open_single_frame(session_id, fidx)
                if result.get("ok"):
                    st.success(f"已開啟幀 #{fidx}")
                else:
                    st.error(f"開啟失敗：{result.get('error')}")


# ── Page ───────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="統一標注平台", layout="wide")

col_title, col_status = st.columns([4, 1])
with col_title:
    st.markdown("## 🗂 統一標注平台")
with col_status:
    db_path = get_db_path()
    st.markdown(
        f"{'🟢'} DB　"
        f"{'🟢' if os.environ.get('MCP_ANNOTATION_URL') else '🔴'} MCP"
    )

st.divider()

# ── Folder selector ────────────────────────────────────────────────────────────

st.markdown("**📁 資料來源**")

# Transfer browsed path before widget renders (Streamlit forbids setting widget key after render)
if "_folder_chosen" in st.session_state:
    st.session_state["folder_input"] = st.session_state.pop("_folder_chosen")

fc1, fc2, fc3 = st.columns([5, 1, 1])
with fc1:
    folder_path = st.text_input(
        "資料夾路徑",
        key="folder_input",
        placeholder="C:/path/to/your/data/folder",
        label_visibility="collapsed",
    )
with fc2:
    if st.button("📂 瀏覽", use_container_width=True):
        try:
            result = subprocess.run(
                [sys.executable, "-c",
                 "import tkinter as tk; from tkinter import filedialog; "
                 "root=tk.Tk(); root.withdraw(); root.wm_attributes('-topmost',True); "
                 "p=filedialog.askdirectory(title='選擇資料夾'); root.destroy(); print(p or '',end='')"],
                capture_output=True, text=True, timeout=60,
            )
            chosen = result.stdout.strip()
            if chosen:
                st.session_state["_folder_chosen"] = chosen
                st.rerun()
        except Exception as e:
            st.warning(f"無法開啟資料夾選擇器：{e}")
with fc3:
    load_clicked = st.button("載入", use_container_width=True, type="primary")

if load_clicked and folder_path:
    with st.spinner("掃描資料夾中..."):
        results = _proc.scan_folder(folder_path)
    st.session_state["folder_path"] = folder_path
    st.success(f"已載入 {len(results)} 個資產")

st.divider()

# ── Filter bar ─────────────────────────────────────────────────────────────────

f1, f2, f3 = st.columns([2, 2, 3])
with f1:
    filter_status = st.selectbox(
        "狀態篩選", ["全部"] + _STATUS_ORDER,
        key="filter_status", label_visibility="collapsed"
    )
with f2:
    filter_types = st.multiselect(
        "類型", ["影片", "圖片"],
        default=["影片", "圖片"], key="filter_types", label_visibility="collapsed"
    )
with f3:
    search_text = st.text_input(
        "搜尋", key="search_text", placeholder="搜尋名稱...", label_visibility="collapsed"
    )

# ── Load assets ────────────────────────────────────────────────────────────────

assets = _proc.load_assets()

type_map = {"影片": "video", "圖片": "image_dir"}
allowed_types = {type_map[t] for t in filter_types}

filtered = [
    a for a in assets
    if (filter_status == "全部" or a["status"] == filter_status)
    and a["asset_type"] in allowed_types
    and (not search_text or search_text.lower() in (a.get("display_name") or "").lower())
]

# ── Master table ───────────────────────────────────────────────────────────────

if not filtered:
    if assets:
        st.info("沒有符合篩選條件的資產。")
    else:
        st.info("請先選擇資料夾並點選「載入」。")
else:
    st.markdown(f"**Annotation Master Table** — 共 {len(filtered)} 筆")
    expanded_session = st.session_state.get("expanded_session")

    for i, asset in enumerate(filtered):
        session_id = asset["session_id"]
        status = asset["status"]
        badge = _STATUS_BADGE.get(status, "❓")
        asset_icon = "🎬" if asset["asset_type"] == "video" else "🖼"
        total = asset.get("total_frames") or 0
        annotated = asset.get("annotation_count") or 0
        name = asset.get("display_name") or Path(asset["file_path"]).name

        summary_raw = asset.get("last_summary")
        summary = json.loads(summary_raw) if summary_raw else None

        row = st.columns([0.4, 3, 0.5, 1.5, 1.2, 2, 1.5])
        with row[0]:
            st.markdown(f"**{i+1}**")
        with row[1]:
            st.markdown(f"{asset_icon} `{name}`")
        with row[2]:
            st.caption(asset_icon)
        with row[3]:
            st.markdown(f"{badge} {status}")
        with row[4]:
            st.caption(f"{annotated}/{total}")
        with row[5]:
            if summary:
                avg_conf = summary.get("avg_confidence", 0)
                obj_counts = summary.get("object_counts", {})
                obj_str = " ".join(f"{k}×{v}" for k, v in list(obj_counts.items())[:3])
                st.caption(f"信心{avg_conf:.2f} {obj_str}")
            else:
                st.caption("—")
        with row[6]:
            _render_action_button(session_id, status, asset, i)

        if expanded_session == session_id and status in ("已標記", "已同步"):
            _render_correction_panel(session_id, asset)

        st.divider()

# ── Bottom bar ─────────────────────────────────────────────────────────────────

pending_sync = [a for a in assets if a["status"] == "已標記"]
sync_label = f"💾 存檔備份（{len(pending_sync)} 筆待同步）"

if st.button(sync_label, disabled=len(pending_sync) == 0, type="primary"):
    st.session_state["show_sync_confirm"] = True

if st.session_state.get("show_sync_confirm"):
    st.warning(f"確認將 {len(pending_sync)} 筆標注結果存入資料庫並移至備份資料夾？")
    cc1, cc2 = st.columns(2)
    with cc1:
        if st.button("✅ 確認存檔", key="confirm_sync"):
            result = _proc.sync_to_db([a["session_id"] for a in pending_sync])
            st.session_state.pop("show_sync_confirm", None)
            st.success(f"已同步 {len(result['synced_session_ids'])} 筆。")
            st.rerun()
    with cc2:
        if st.button("❌ 取消", key="cancel_sync"):
            st.session_state.pop("show_sync_confirm", None)
            st.rerun()

# ── Auto-refresh and PID monitoring ───────────────────────────────────────────

# Sessions being tracked (video worker running) or awaiting xany launch (xany_pid not set yet)
needs_xany_launch = [
    a for a in assets
    if a["status"] in ("追蹤中", "標記中") and not a.get("xany_pid")
]
for a in needs_xany_launch:
    poll_result = _proc.poll_tracking_status(a["session_id"])
    if poll_result.get("status") == "xany_launched":
        st.rerun()
    elif poll_result.get("status") == "xany_launch_failed":
        st.error(f"X-AnyLabeling 啟動失敗：{poll_result.get('error')}")

# Sessions where X-AnyLabeling is open — monitor PID
labeling_sessions = [a for a in assets if a["status"] == "標記中" and a.get("xany_pid")]

need_refresh = bool(needs_xany_launch or labeling_sessions)
if need_refresh:
    st_autorefresh(interval=2000, key="master_poll")

    import psutil
    for a in labeling_sessions:
        if not psutil.pid_exists(a["xany_pid"]):
            _proc.update_after_xany_close(a["session_id"])
            next_id = _proc.get_next_unannotated()
            if next_id:
                st.session_state["focus_session"] = next_id
            st.rerun()
