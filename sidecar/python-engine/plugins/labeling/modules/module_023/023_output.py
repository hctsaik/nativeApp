from __future__ import annotations

import os
from pathlib import Path

import streamlit as st


def _get_service():
    from plugins.labeling.domain.services import AnnotationService
    from plugins.labeling.domain.storage.workspace import AnnotationWorkspace
    ws_path = Path(os.environ.get("CIM_LOG_DIR", "/tmp")) / "annotation_workspace"
    return AnnotationService(AnnotationWorkspace(ws_path))


_ANT_ACTIVE_COLOR = {0: "⚪", 1: "🟠", 2: "🟢"}
_ANT_ACTIVE_LABEL = {0: "待標注", 1: "標注中", 2: "已完成"}


def render_output(result: dict = None) -> None:
    st.title("📋 標註任務 — 進行中")
    st.caption("已認領但尚未完成的任務（antActive = 1：標注中）。")

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
        key="m023_out_selected_tenant",
    )
    tenant_id = tenant_options[selected_label]["tenant_id"]

    if st.button("🔄 重新整理", key="m023_out_refresh"):
        st.session_state.pop(f"m023_out_tasks_{tenant_id}", None)

    if f"m023_out_tasks_{tenant_id}" not in st.session_state:
        try:
            tasks = service.list_tasks(tenant_id, ant_active=1)
            st.session_state[f"m023_out_tasks_{tenant_id}"] = tasks
        except Exception as exc:
            st.error(f"❌ 無法載入任務清單：{exc}")
            st.session_state[f"m023_out_tasks_{tenant_id}"] = []

    tasks: list[dict] = st.session_state.get(f"m023_out_tasks_{tenant_id}", [])

    if not tasks:
        st.info("目前無「標注中」任務。")
        return

    st.write(f"**標注中任務（{len(tasks)} 筆）：**")
    for task in tasks:
        ant_active = task.get("ant_active", 1)
        icon = _ANT_ACTIVE_COLOR.get(ant_active, "🟠")
        label = _ANT_ACTIVE_LABEL.get(ant_active, str(ant_active))
        st.markdown(
            f"{icon} **{task['ant_id']}** — {label} "
            f"｜ 標注人員：`{task.get('annotated_by') or '—'}` "
            f"｜ task_id: `{task['task_id'][:8]}…`"
        )
