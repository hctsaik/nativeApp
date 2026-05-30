from __future__ import annotations

import os
from pathlib import Path

import streamlit as st


def _get_service():
    from plugins.labeling.domain.services import AnnotationService
    from plugins.labeling.domain.storage.workspace import AnnotationWorkspace
    ws_path = Path(os.environ.get("CIM_LOG_DIR", "/tmp")) / "annotation_workspace"
    return AnnotationService(AnnotationWorkspace(ws_path))


def _mask_token(token: str | None) -> str:
    if not token:
        return "（未設定）"
    if len(token) <= 4:
        return "****"
    return f"****...{token[-4:]}"


def render_output(result: dict = None) -> None:
    st.title("🔐 標註權限管理 — 概覽")

    if st.button("🔄 重新整理", key="m022_out_refresh"):
        st.session_state.pop("m022_out_tenant_list", None)

    service = _get_service()

    if "m022_out_tenant_list" not in st.session_state:
        try:
            st.session_state["m022_out_tenant_list"] = service.list_tenants()
        except Exception as exc:
            st.error(f"❌ 無法載入 Tenant 清單：{exc}")
            st.session_state["m022_out_tenant_list"] = []

    tenants: list[dict] = st.session_state.get("m022_out_tenant_list", [])

    if not tenants:
        st.info("目前尚無已註冊的 Tenant。請至左側頁面新增。")
        return

    for tenant in tenants:
        tenant_id = tenant["tenant_id"]
        with st.container():
            st.markdown(
                f"### 🏢 {tenant['system_name']}"
                f"\n`{tenant_id}`"
            )
            col1, col2, col3 = st.columns(3)
            col1.metric("AOI 系統位址", tenant["server_host_name"])
            col2.metric("標注結果格式", tenant["target_format"])
            col3.metric("API 金鑰", _mask_token(tenant.get("api_token")))

            # 授權使用者
            try:
                users = service.list_tenant_users(tenant_id)
                if users:
                    with st.expander(f"授權使用者（{len(users)} 人）"):
                        for u in users:
                            st.markdown(f"- `{u['user_id']}`")
                else:
                    st.caption("尚無授權使用者。")
            except Exception as exc:
                st.caption(f"無法載入使用者：{exc}")

            st.divider()
