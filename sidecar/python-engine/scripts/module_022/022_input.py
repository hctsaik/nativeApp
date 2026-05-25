from __future__ import annotations

import importlib.util as _ilu
import os
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent

_proc_spec = _ilu.spec_from_file_location("_022_process", _HERE / "022_process.py")
_proc = _ilu.module_from_spec(_proc_spec)
_proc_spec.loader.exec_module(_proc)


def _get_service():
    from annotation.services import AnnotationService
    from annotation.storage.workspace import AnnotationWorkspace
    ws_path = Path(os.environ.get("CIM_LOG_DIR", "/tmp")) / "annotation_workspace"
    return AnnotationService(AnnotationWorkspace(ws_path))


def render_input() -> dict:
    st.title("🏢 Tenant 管理")
    st.caption("新增外部系統連線設定（SystemTenant）並管理授權使用者白名單。")

    service = _get_service()

    # ── Section 1: 新增 Tenant ────────────────────────────────────────────────
    st.subheader("1. 新增 Tenant")

    with st.form("m022_add_tenant_form"):
        system_name = st.text_input(
            "系統名稱 (system_name)",
            key="m022_form_system_name",
            placeholder="AOI-Line-1",
        )
        server_host_name = st.text_input(
            "伺服器位址 (server_host_name)",
            key="m022_form_server_host",
            placeholder="http://aoi-server:8080 或 fake://test",
        )
        target_format = st.selectbox(
            "目標格式 (target_format)",
            options=["coco", "yolo-detection", "labelme", "isat"],
            key="m022_form_target_format",
        )
        api_token = st.text_input(
            "API Token（可留空）",
            type="password",
            key="m022_form_api_token",
        )
        submitted = st.form_submit_button("➕ 新增 Tenant")

    if submitted:
        if not system_name.strip():
            st.error("❌ 系統名稱不可空白。")
        elif not server_host_name.strip():
            st.error("❌ 伺服器位址不可空白。")
        else:
            try:
                result = service.register_tenant(
                    system_name=system_name.strip(),
                    server_host_name=server_host_name.strip(),
                    target_format=target_format,
                    api_token=api_token.strip() or None,
                )
                st.success(f"✅ 已新增 Tenant：{result['system_name']}（tenant_id: {result['tenant_id']}）")
                st.session_state.pop("m022_tenant_list", None)
            except Exception as exc:
                st.error(f"❌ 新增失敗：{exc}")

    st.divider()

    # ── Section 2: 現有 Tenant 列表 ──────────────────────────────────────────
    st.subheader("2. 現有 Tenant")

    if st.button("🔄 重新整理清單", key="m022_refresh_list"):
        st.session_state.pop("m022_tenant_list", None)

    if "m022_tenant_list" not in st.session_state:
        try:
            st.session_state["m022_tenant_list"] = service.list_tenants()
        except Exception as exc:
            st.error(f"❌ 無法載入 Tenant 清單：{exc}")
            st.session_state["m022_tenant_list"] = []

    tenants: list[dict] = st.session_state.get("m022_tenant_list", [])

    if not tenants:
        st.info("目前尚無已註冊的 Tenant。")
        return {"mode": "idle"}

    tenant_options = {f"{t['system_name']} ({t['tenant_id'][:8]}…)": t for t in tenants}
    selected_label = st.selectbox(
        "選擇 Tenant",
        options=list(tenant_options.keys()),
        key="m022_selected_tenant",
    )
    selected_tenant = tenant_options[selected_label]
    tenant_id = selected_tenant["tenant_id"]

    st.divider()

    # ── Section 3: 白名單管理 ─────────────────────────────────────────────────
    st.subheader("3. 使用者白名單")

    col_uid, col_btn = st.columns([3, 1])
    with col_uid:
        new_user_id = st.text_input(
            "使用者 ID（工號）",
            key="m022_new_user_id",
            placeholder="user001",
        )
    with col_btn:
        st.write("")  # 對齊
        add_user_btn = st.button("➕ 新增使用者", key="m022_add_user_btn")

    if add_user_btn:
        if not new_user_id.strip():
            st.error("❌ 使用者 ID 不可空白。")
        else:
            try:
                service.add_user_to_tenant(tenant_id, new_user_id.strip())
                st.success(f"✅ 已新增使用者：{new_user_id.strip()}")
                st.session_state.pop(f"m022_users_{tenant_id}", None)
            except Exception as exc:
                st.error(f"❌ 新增失敗：{exc}")

    # 顯示目前白名單
    if f"m022_users_{tenant_id}" not in st.session_state:
        try:
            st.session_state[f"m022_users_{tenant_id}"] = service.list_tenant_users(tenant_id)
        except Exception as exc:
            st.error(f"❌ 無法載入白名單：{exc}")
            st.session_state[f"m022_users_{tenant_id}"] = []

    users: list[dict] = st.session_state.get(f"m022_users_{tenant_id}", [])
    if users:
        st.write(f"**目前授權使用者（{len(users)} 人）：**")
        for u in users:
            st.markdown(f"- `{u['user_id']}`")
    else:
        st.info("此 Tenant 尚無授權使用者。")

    return {"mode": "idle"}
