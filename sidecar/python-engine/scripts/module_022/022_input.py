from __future__ import annotations

import importlib.util as _ilu
import os
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent

_proc_spec = _ilu.spec_from_file_location("_022_process", _HERE / "022_process.py")
_proc = _ilu.module_from_spec(_proc_spec)
_proc_spec.loader.exec_module(_proc)

_ui_spec = _ilu.spec_from_file_location("_ui_components", _HERE.parent / "shared" / "ui_components.py")
_ui = _ilu.module_from_spec(_ui_spec)
_ui_spec.loader.exec_module(_ui)


def _get_service():
    from plugins.labeling.domain.services import AnnotationService
    from plugins.labeling.domain.storage.workspace import AnnotationWorkspace
    ws_path = Path(os.environ.get("CIM_LOG_DIR", "/tmp")) / "annotation_workspace"
    return AnnotationService(AnnotationWorkspace(ws_path))


def render_input() -> dict:
    _ui.inject_streamlit_zh_overrides()
    st.title("🔐 系統連線設定")
    st.caption("新增外部系統連線並管理各任務的授權使用者。")
    st.info("⚙️ **此頁面由系統管理員設定**。標注員請直接前往「待認領任務」認領任務，無需操作本頁面。")

    service = _get_service()

    if "m022_add_success" in st.session_state:
        st.success(st.session_state.pop("m022_add_success"))

    if "m022_delete_success" in st.session_state:
        st.success(st.session_state.pop("m022_delete_success"))

    # ── Section 1：選擇外部系統 ───────────────────────────────────────────────
    st.subheader("1. 選擇外部系統")

    col_refresh, _ = st.columns([2, 6])
    if col_refresh.button("🔄 重新整理", key="m022_refresh_list"):
        st.session_state.pop("m022_tenant_list", None)

    if "m022_tenant_list" not in st.session_state:
        try:
            st.session_state["m022_tenant_list"] = service.list_tenants()
        except Exception as exc:
            st.error(f"❌ 無法載入連線清單：{exc}")
            st.session_state["m022_tenant_list"] = []

    tenants: list[dict] = st.session_state.get("m022_tenant_list", [])

    if not tenants:
        st.info("目前尚無已新增的外部系統連線。請至下方「新增外部系統連線」區塊建立第一個連線。")
        st.divider()
        _render_add_tenant_form(service)
        return {"mode": "idle"}

    # 已連線系統清單（每筆旁邊有刪除按鈕）
    st.write("**已連線的外部系統：**")
    pending_delete_id = st.session_state.get("m022_pending_delete_tenant_id")
    for t in tenants:
        tid = t["tenant_id"]
        col_name, col_del = st.columns([7, 1])
        col_name.markdown(f"- **{t['system_name']}** `{tid[:8]}…` — {t['server_host_name']}")
        if col_del.button("🗑️", key=f"m022_del_tenant_{tid}", help="刪除此連線"):
            st.session_state["m022_pending_delete_tenant_id"] = tid
            st.rerun()

    if pending_delete_id:
        pending_tenant = next((t for t in tenants if t["tenant_id"] == pending_delete_id), None)
        if pending_tenant:
            st.warning(
                f"⚠️ 確認刪除連線「**{pending_tenant['system_name']}**」？"
                "此操作將一併刪除所有授權使用者對應與任務記錄，且無法復原。"
            )
            col_confirm, col_cancel, _ = st.columns([2, 2, 4])
            if col_confirm.button("✅ 確認刪除", key="m022_confirm_delete_tenant"):
                try:
                    service.delete_tenant(pending_delete_id)
                    st.session_state["m022_delete_success"] = (
                        f"✅ 已刪除連線：{pending_tenant['system_name']}"
                    )
                    st.session_state.pop("m022_pending_delete_tenant_id", None)
                    st.session_state.pop("m022_tenant_list", None)
                    for k in list(st.session_state.keys()):
                        if pending_delete_id in k:
                            st.session_state.pop(k, None)
                    st.rerun()
                except Exception as exc:
                    st.error(f"❌ 刪除失敗：{exc}")
            if col_cancel.button("❌ 取消", key="m022_cancel_delete_tenant"):
                st.session_state.pop("m022_pending_delete_tenant_id", None)
                st.rerun()

    st.divider()

    tenant_options = {f"{t['system_name']} ({t['tenant_id'][:8]}…)": t for t in tenants}
    selected_label = st.selectbox(
        "選擇要操作的外部系統",
        options=list(tenant_options.keys()),
        key="m022_selected_tenant",
    )
    selected_tenant = tenant_options[selected_label]
    tenant_id = selected_tenant["tenant_id"]

    st.divider()

    # ── Section 2：選擇任務 ───────────────────────────────────────────────────
    st.subheader("2. 選擇任務")

    tasks_cache_key = f"m022_tasks_{tenant_id}"
    if tasks_cache_key not in st.session_state:
        try:
            st.session_state[tasks_cache_key] = service.get_ant_list(tenant_id)
        except Exception:
            st.session_state[tasks_cache_key] = []

    restriction_map_key = f"m022_restrictions_{tenant_id}"
    if restriction_map_key not in st.session_state:
        try:
            st.session_state[restriction_map_key] = service.get_task_restriction_map(tenant_id)
        except Exception:
            st.session_state[restriction_map_key] = {}

    restriction_map: dict = st.session_state.get(restriction_map_key, {})
    tasks: list[dict] = st.session_state.get(tasks_cache_key, [])

    if not tasks:
        st.info("此系統目前尚無任務資料。請確認外部系統已正常運作。")
        st.divider()
        _render_add_tenant_form(service)
        return {"mode": "idle"}

    task_options: dict[str, str] = {}
    for t in tasks:
        ant_id_val: str = t["ant_id"]
        restricted_users = restriction_map.get(ant_id_val, [])
        if restricted_users:
            label = f"🔒 {ant_id_val}（限定 {len(restricted_users)} 人）"
        else:
            label = f"🔓 {ant_id_val}（開放所有人）"
        if t.get("ant_period"):
            label += f" · {t['ant_period'][:10]}"
        task_options[label] = ant_id_val

    selected_task_label = st.selectbox(
        "任務",
        options=list(task_options.keys()),
        key="m022_selected_task",
        help="🔒 表示已限定授權使用者；🔓 表示所有人均可認領。",
    )
    selected_ant_id: str = task_options[selected_task_label]

    st.divider()

    # ── Section 3：授權使用者管理 ─────────────────────────────────────────────
    st.subheader("3. 授權使用者管理")
    st.caption(f"目前任務：**{selected_ant_id}**（所屬系統：{selected_tenant['system_name']}）")

    users_cache_key = f"m022_users_{tenant_id}_{selected_ant_id}"
    if users_cache_key not in st.session_state:
        try:
            st.session_state[users_cache_key] = service.list_tenant_users(tenant_id, ant_id=selected_ant_id)
        except Exception as exc:
            st.error(f"❌ 無法載入授權清單：{exc}")
            st.session_state[users_cache_key] = []

    users: list[dict] = st.session_state.get(users_cache_key, [])

    if users:
        st.write(f"**已授權使用者（{len(users)} 人）：**")
        for u in users:
            col_uid, col_del = st.columns([5, 1])
            col_uid.markdown(f"- `{u['user_id']}`")
            del_key = f"m022_del_{tenant_id}_{selected_ant_id}_{u['user_id']}"
            if col_del.button("✕", key=del_key, help="移除授權"):
                try:
                    service.remove_user_from_tenant(tenant_id, u["user_id"], ant_id=selected_ant_id)
                    st.session_state.pop(users_cache_key, None)
                    st.session_state.pop(restriction_map_key, None)
                    st.rerun()
                except Exception as exc:
                    st.error(f"❌ 移除失敗：{exc}")
    else:
        st.info(f"任務 `{selected_ant_id}` 尚未設定使用者限制，目前**所有人均可認領**此任務。")

    col_uid, col_btn = st.columns([3, 1])
    with col_uid:
        new_user_id = st.text_input(
            "新增使用者 ID（工號）",
            key="m022_new_user_id",
            placeholder="user001",
        )
    with col_btn:
        st.write("")
        add_user_btn = st.button("➕ 新增", key="m022_add_user_btn")

    if add_user_btn:
        if not new_user_id.strip():
            st.error("❌ 使用者 ID 不可空白。")
        else:
            try:
                service.add_user_to_tenant(tenant_id, new_user_id.strip(), ant_id=selected_ant_id)
                st.success(f"✅ 已將 `{new_user_id.strip()}` 加入任務 {selected_ant_id} 的授權清單。")
                st.session_state.pop(users_cache_key, None)
                st.session_state.pop(restriction_map_key, None)
                st.rerun()
            except Exception as exc:
                st.error(f"❌ 新增失敗：{exc}")

    st.divider()

    # ── Section 4：新增外部系統連線 ───────────────────────────────────────────
    _render_add_tenant_form(service)

    return {"mode": "idle"}


def _render_add_tenant_form(service) -> None:
    with st.expander("4. 新增外部系統連線", expanded=False):
        with st.form("m022_add_tenant_form"):
            system_name = st.text_input(
                "連線別名",
                key="m022_form_system_name",
                placeholder="AOI-Line-1",
            )
            server_host_name = st.text_input(
                "AOI 系統位址",
                key="m022_form_server_host",
                placeholder="http://aoi-server:8080",
            )
            target_format = st.selectbox(
                "標注結果格式",
                options=["coco", "yolo-detection", "labelme", "isat"],
                key="m022_form_target_format",
            )
            st.caption("建議選 coco，不確定時請詢問 IT。")
            api_token = st.text_input(
                "API 金鑰（可留空）",
                type="password",
                key="m022_form_api_token",
                placeholder="Bearer eyJ... 或由 IT 提供",
            )
            submitted = st.form_submit_button("➕ 新增連線")

        if submitted:
            if not system_name.strip():
                st.error("❌ 連線別名不可空白。")
            elif not server_host_name.strip():
                st.error("❌ AOI 系統位址不可空白。")
            else:
                try:
                    result = service.register_tenant(
                        system_name=system_name.strip(),
                        server_host_name=server_host_name.strip(),
                        target_format=target_format,
                        api_token=api_token.strip() or None,
                    )
                    st.session_state["m022_add_success"] = (
                        f"✅ 已新增連線：{result['system_name']}（ID: {result['tenant_id'][:8]}…）"
                    )
                    st.session_state.pop("m022_tenant_list", None)
                    for k in ("m022_form_system_name", "m022_form_server_host", "m022_form_api_token"):
                        st.session_state.pop(k, None)
                    st.rerun()
                except Exception as exc:
                    st.error(f"❌ 新增失敗：{exc}")
