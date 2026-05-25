from __future__ import annotations

import os
from pathlib import Path

import streamlit as st


def _get_service():
    from annotation.services import AnnotationService
    from annotation.storage.workspace import AnnotationWorkspace
    ws_path = Path(os.environ.get("CIM_LOG_DIR", "/tmp")) / "annotation_workspace"
    return AnnotationService(AnnotationWorkspace(ws_path))


def render_input() -> dict:
    st.title("📊 完成報表")
    st.caption("CIM Sponsor Dashboard — 標注進度統計與結果 ZIP 下載。")

    service = _get_service()

    # ── Tenant 選擇 ──────────────────────────────────────────────────────────
    try:
        tenants = service.list_tenants()
    except Exception as exc:
        st.error(f"❌ 無法載入 Tenant 清單：{exc}")
        return {"mode": "idle"}

    if not tenants:
        st.warning("尚無已註冊的 Tenant，請先至「Tenant 管理」頁面新增。")
        return {"mode": "idle"}

    tenant_options = {f"{t['system_name']} ({t['tenant_id'][:8]}…)": t for t in tenants}
    selected_label = st.selectbox(
        "選擇 Tenant",
        options=list(tenant_options.keys()),
        key="m025_selected_tenant",
    )
    tenant_id = tenant_options[selected_label]["tenant_id"]

    # ── 更新統計 ─────────────────────────────────────────────────────────────
    if st.button("🔄 更新統計", key="m025_refresh_stats"):
        st.session_state.pop(f"m025_stats_{tenant_id}", None)
        st.session_state.pop(f"m025_completed_tasks_{tenant_id}", None)

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
        col1.metric("⚪ 待標注", stats.get("pending", 0))
        col2.metric("🟠 標注中", stats.get("processing", 0))
        col3.metric("🟢 已完成", stats.get("completed", 0))
        st.caption(f"合計：{stats.get('total', 0)} 筆任務")

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

    for task in completed_tasks:
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
                mode = st.selectbox(
                    "匯出模式",
                    options=["orig_img_orig_ant", "orig_img_new_ant"],
                    key=mode_key,
                    label_visibility="collapsed",
                )
            with col_dl:
                dl_key = f"m025_dl_{task_id}"
                if dl_key not in st.session_state:
                    if st.button("📦 下載 ZIP", key=f"m025_dlbtn_{task_id}"):
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
