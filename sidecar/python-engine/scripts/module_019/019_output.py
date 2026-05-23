from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path

import streamlit as st
from streamlit_autorefresh import st_autorefresh

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_019_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_STATUS_COLOR = {
    "needs_review": "🟡",
    "empty": "🔴",
    "annotated": "🟢",
}
_STATUS_LABEL = {
    "needs_review": "需複核",
    "empty": "未標注",
    "annotated": "已完成",
}


def render_output() -> None:
    result: dict = st.session_state.get("last_result", {})
    mode = result.get("mode", "idle")

    # ── 進行中：自動刷新 + 顯示進度 ──────────────────────────────────────────
    if mode == "idle" or not result:
        progress = _cfg.read_progress()
        if progress and progress.get("running"):
            st_autorefresh(interval=800, limit=None, key="m019_refresh")
            st.info("⏳ 下載中，請稍候…")
            phase = progress.get("phase", "")
            current = progress.get("current", "")
            if current:
                st.caption(f"{phase}：{current}")
            elif phase:
                st.caption(phase)
            return
        st.info("請在左側設定 Service URL 並選擇資料集，然後按「執行」開始下載。")
        return

    # ── 錯誤 ─────────────────────────────────────────────────────────────────
    if mode == "error":
        st.error(f"❌ {result.get('error', '未知錯誤')}")
        return

    # ── 完成 ─────────────────────────────────────────────────────────────────
    local_dir = result.get("local_dir", "")
    total = result.get("total", 0)
    needs_review = result.get("needs_review", 0)
    empty = result.get("empty", 0)
    annotated = result.get("annotated", 0)
    dataset_name = result.get("dataset_name", "")

    st.success(f"✅ 已下載完成：**{dataset_name}**")

    # 摘要指標
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("總張數", total)
    col2.metric("🔴 未標注", empty)
    col3.metric("🟡 需複核", needs_review)
    col4.metric("🟢 已完成", annotated)

    st.divider()

    # 命名衝突警告
    conflicts = result.get("conflicts", [])
    if conflicts:
        with st.expander(f"⚠️ 命名衝突（{len(conflicts)} 個）", expanded=False):
            for c in conflicts:
                st.code(c)
            st.caption("annotations/ 的 .json 已覆蓋同名檔案（這通常是正確行為）。")

    # ── 下一步引導 ────────────────────────────────────────────────────────────
    st.subheader("下一步")
    st.info(
        "📦 請前往 **Data Feeder**（第 2 個 Tab），"
        "資料夾路徑已自動填入，按「執行」載入後即可開始標注。"
    )
    st.code(local_dir, language=None)

    if st.button("📋 複製路徑", key="m019_copy_path"):
        st.session_state["_m019_copied"] = True
        st.write(
            f'<script>navigator.clipboard.writeText("{local_dir}")</script>',
            unsafe_allow_html=True,
        )
    if st.session_state.get("_m019_copied"):
        st.caption("✓ 已複製到剪貼簿")

    st.divider()

    # ── Item 清單（分頁） ─────────────────────────────────────────────────────
    item_statuses: list[dict] = result.get("item_statuses", [])
    if not item_statuses:
        return

    # 狀態篩選
    filter_opts = ["全部", "🔴 未標注", "🟡 需複核", "🟢 已完成"]
    filter_map = {"全部": None, "🔴 未標注": "empty", "🟡 需複核": "needs_review", "🟢 已完成": "annotated"}
    chosen_filter = st.radio("篩選", filter_opts, horizontal=True, key="m019_filter")
    filter_status = filter_map[chosen_filter]

    visible = [i for i in item_statuses if filter_status is None or i["status"] == filter_status]

    PAGE_SIZE = 50
    n_pages = max(1, (len(visible) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = st.session_state.get("m019_page", 0)
    page = min(page, n_pages - 1)

    if n_pages > 1:
        col_prev, col_info, col_next = st.columns([1, 3, 1])
        with col_prev:
            if st.button("← 上一頁", disabled=page == 0, key="m019_prev"):
                st.session_state["m019_page"] = page - 1
                st.rerun()
        with col_info:
            st.caption(f"第 {page + 1} / {n_pages} 頁（共 {len(visible)} 筆）")
        with col_next:
            if st.button("下一頁 →", disabled=page == n_pages - 1, key="m019_next"):
                st.session_state["m019_page"] = page + 1
                st.rerun()

    page_items = visible[page * PAGE_SIZE: (page + 1) * PAGE_SIZE]
    for item in page_items:
        icon = _STATUS_COLOR.get(item["status"], "⬜")
        label = _STATUS_LABEL.get(item["status"], item["status"])
        st.markdown(f"{icon} `{item['file_name']}` — **{label}**")
