from __future__ import annotations

import importlib.util as _ilu
import os
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent
_ui_spec = _ilu.spec_from_file_location("_ui_components", _HERE.parent / "shared" / "ui_components.py")
_ui = _ilu.module_from_spec(_ui_spec)
_ui_spec.loader.exec_module(_ui)


def _get_service():
    from annotation.services import AnnotationService
    from annotation.storage.workspace import AnnotationWorkspace
    ws_path = Path(os.environ.get("CIM_LOG_DIR", "/tmp")) / "annotation_workspace"
    return AnnotationService(AnnotationWorkspace(ws_path))


_EXPORT_MODE_LABELS = {
    "orig_img_orig_ant": "原始標注歸檔（含原始影像 + iWISC 原始標注）",
    "orig_img_new_ant":  "最新標注結果（含原始影像 + 標注員修改版）",
}


def render_input() -> dict:
    _ui.inject_streamlit_zh_overrides()
    st.title("📊 完成報表")
    st.caption("標注進度總覽 — 標注進度統計與結果 ZIP 下載。")

    service = _get_service()

    # ── Tenant 選擇 ──────────────────────────────────────────────────────────
    try:
        tenants = service.list_tenants()
    except Exception as exc:
        st.error(f"❌ 無法載入 Tenant 清單：{exc}")
        return {"mode": "idle"}

    if not tenants:
        st.warning("尚無已註冊的 Tenant，請先至「標註權限管理」頁面新增。")
        return {"mode": "idle"}

    tenant_options = {f"{t['system_name']} ({t['tenant_id'][:8]}…)": t for t in tenants}
    selected_label = st.selectbox(
        "選擇外部系統",
        options=list(tenant_options.keys()),
        key="m025_selected_tenant",
    )
    tenant_id = tenant_options[selected_label]["tenant_id"]

    # ── 更新統計 ─────────────────────────────────────────────────────────────
    if st.button("🔄 更新統計", key="m025_refresh_stats"):
        st.session_state.pop(f"m025_stats_{tenant_id}", None)
        st.session_state.pop(f"m025_completed_tasks_{tenant_id}", None)
        st.session_state.pop(f"m025_page_{tenant_id}", None)  # 重設頁碼回第 1 頁

    if f"m025_stats_{tenant_id}" not in st.session_state:
        try:
            stats = service.get_dashboard_stats(tenant_id)
            st.session_state[f"m025_stats_{tenant_id}"] = stats
        except Exception as exc:
            st.error(f"❌ 無法取得統計：{exc}")
            st.session_state[f"m025_stats_{tenant_id}"] = None

    stats = st.session_state.get(f"m025_stats_{tenant_id}")

    if stats:
        st.divider()
        st.subheader("進度統計")
        col1, col2, col3 = st.columns(3)
        pending = stats.get("pending", 0)
        in_progress = stats.get("processing", 0)
        completed = stats.get("completed", 0)
        col1.metric("⚪ 待標注", pending)
        col2.metric("🟠 標注中", in_progress)
        col3.metric("🟢 已完成", completed)
        st.caption(f"合計：{stats.get('total', 0)} 筆任務")
        total = pending + in_progress + completed
        if total > 0:
            pct = int(completed / total * 100)
            st.progress(pct / 100, text=f"完成率 {pct}%（{completed}/{total}）")

    st.divider()

    # ── 已完成任務列表 + ZIP 下載 ─────────────────────────────────────────────
    st.subheader("已完成任務")

    if f"m025_completed_tasks_{tenant_id}" not in st.session_state:
        try:
            completed = service.list_tasks(tenant_id, ant_active=2)
            st.session_state[f"m025_completed_tasks_{tenant_id}"] = completed
        except Exception as exc:
            st.error(f"❌ 無法載入已完成任務：{exc}")
            st.session_state[f"m025_completed_tasks_{tenant_id}"] = []

    completed_tasks: list[dict] = st.session_state.get(f"m025_completed_tasks_{tenant_id}", [])

    if not completed_tasks:
        st.info("目前無已完成任務。")
        return {"mode": "idle"}

    _PAGE_SIZE = 50
    _total_pages = max(1, (len(completed_tasks) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    _page_key = f"m025_page_{tenant_id}"
    if _page_key not in st.session_state:
        st.session_state[_page_key] = 0
    _page = st.session_state[_page_key]
    _page = max(0, min(_page, _total_pages - 1))
    st.session_state[_page_key] = _page  # 確保 clamp 結果持久化

    if _total_pages > 1:
        col_prev, col_info, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("◀ 上一頁", disabled=(_page == 0), key=f"m025_prev_{tenant_id}"):
                st.session_state[_page_key] = _page - 1
                st.rerun()
        with col_info:
            st.caption(f"第 {_page + 1} / {_total_pages} 頁（共 {len(completed_tasks)} 筆）")
        with col_next:
            if st.button("下一頁 ▶", disabled=(_page == _total_pages - 1), key=f"m025_next_{tenant_id}"):
                st.session_state[_page_key] = _page + 1
                st.rerun()

    _start = _page * _PAGE_SIZE
    _page_tasks = completed_tasks[_start: _start + _PAGE_SIZE]

    for task in _page_tasks:
        task_id = task["task_id"]
        ant_id = task.get("ant_id", "—")
        annotated_by = task.get("annotated_by") or "—"
        updated_at = task.get("updated_at", "—")

        with st.container():
            col_info, col_mode, col_dl = st.columns([3, 2, 2])
            with col_info:
                st.markdown(f"🟢 **{ant_id}**")
                st.caption(f"標注人員：`{annotated_by}` ｜ 完成時間：{updated_at}")
                st.caption(f"task_id: `{task_id[:12]}…`")
            with col_mode:
                mode_key = f"m025_mode_{task_id}"
                st.caption("匯出模式")
                mode = st.selectbox(
                    "匯出模式",
                    options=list(_EXPORT_MODE_LABELS.keys()),
                    format_func=lambda x: _EXPORT_MODE_LABELS.get(x, x),
                    key=mode_key,
                    label_visibility="collapsed",
                )
            with col_dl:
                dl_key = f"m025_dl_{task_id}"
                if dl_key not in st.session_state:
                    if st.button("📦 產生 ZIP", key=f"m025_dlbtn_{task_id}"):
                        with st.spinner("正在產生 ZIP 檔案，請稍候..."):
                            try:
                                zip_bytes = service.export_result_zip(task_id, mode)
                                st.session_state[dl_key] = zip_bytes
                                st.rerun()
                            except Exception as exc:
                                st.error(f"❌ 匯出失敗：{exc}")
                else:
                    zip_bytes = st.session_state[dl_key]
                    st.download_button(
                        label="⬇️ 儲存 ZIP",
                        data=zip_bytes,
                        file_name=f"{ant_id}_{mode}.zip",
                        mime="application/zip",
                        key=f"m025_save_{task_id}",
                    )

        st.markdown("---")

    return {"mode": "idle"}
