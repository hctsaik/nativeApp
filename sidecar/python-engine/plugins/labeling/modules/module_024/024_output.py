from __future__ import annotations

import os
from pathlib import Path

import streamlit as st


def _get_service():
    from plugins.labeling.domain.services import AnnotationService
    from plugins.labeling.domain.storage.workspace import AnnotationWorkspace
    ws_path = Path(os.environ.get("CIM_LOG_DIR", "/tmp")) / "annotation_workspace"
    return AnnotationService(AnnotationWorkspace(ws_path))


def render_output(result: dict = None) -> None:
    st.title("✏️ 標注工作台 — 已完成任務")
    st.caption("已標記完成（antActive = 2）的任務摘要。")

    service = _get_service()

    # Tenant 選擇
    try:
        tenants = service.list_tenants()
    except Exception as exc:
        st.error(f"❌ 無法載入 Tenant 清單：{exc}")
        return

    if not tenants:
        st.info("尚無已註冊的 Tenant。")
        return

    tenant_options = {f"{t['system_name']} ({t['tenant_id'][:8]}…)": t for t in tenants}
    selected_label = st.selectbox(
        "選擇外部系統",
        options=list(tenant_options.keys()),
        key="m024_out_selected_tenant",
    )
    tenant_id = tenant_options[selected_label]["tenant_id"]

    if st.button("🔄 重新整理", key="m024_out_refresh"):
        st.session_state.pop(f"m024_out_tasks_{tenant_id}", None)

    if f"m024_out_tasks_{tenant_id}" not in st.session_state:
        try:
            tasks = service.list_tasks(tenant_id, ant_active=2)
            st.session_state[f"m024_out_tasks_{tenant_id}"] = tasks
        except Exception as exc:
            st.error(f"❌ 無法載入任務：{exc}")
            st.session_state[f"m024_out_tasks_{tenant_id}"] = []

    tasks: list[dict] = st.session_state.get(f"m024_out_tasks_{tenant_id}", [])

    if not tasks:
        st.info("目前無已完成任務。")
        return

    st.write(f"**已完成任務（{len(tasks)} 筆）：**")
    for task in tasks:
        cols = st.columns([2, 2, 3, 3])
        cols[0].markdown(f"🟢 **{task['ant_id']}**")
        cols[1].caption(f"標注人員：`{task.get('annotated_by') or '—'}`")
        cols[2].caption(f"完成時間：{task.get('updated_at', '—')}")
        cols[3].caption(f"task_id: `{task['task_id'][:12]}…`")
