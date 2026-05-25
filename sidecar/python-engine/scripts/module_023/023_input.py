from __future__ import annotations

import os
from pathlib import Path

import streamlit as st


def _get_service():
    from annotation.services import AnnotationService
    from annotation.storage.workspace import AnnotationWorkspace
    ws_path = Path(os.environ.get("CIM_LOG_DIR", "/tmp")) / "annotation_workspace"
    return AnnotationService(AnnotationWorkspace(ws_path))


_ANT_ACTIVE_LABEL = {0: "待標注", 1: "標注中", 2: "已完成"}
_ANT_ACTIVE_ICON = {0: "⚪", 1: "🟠", 2: "🟢"}


def render_input() -> dict:
    st.title("📋 公海任務")
    st.caption("瀏覽外部系統的待標注任務清單並認領任務。")

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
        key="m023_selected_tenant",
    )
    selected_tenant = tenant_options[selected_label]
    tenant_id = selected_tenant["tenant_id"]

    # ── user_id 輸入 ─────────────────────────────────────────────────────────
    user_id = st.text_input(
        "您的使用者 ID（工號）",
        key="m023_user_id",
        placeholder="user001",
    )

    # ── 取得任務清單 ──────────────────────────────────────────────────────────
    col_btn, _ = st.columns([2, 5])
    with col_btn:
        fetch_btn = st.button("🔄 取得任務清單", key="m023_fetch_tasks")

    if fetch_btn:
        if not user_id.strip():
            st.error("❌ 請先填入您的使用者 ID。")
        else:
            try:
                tasks = service.get_ant_list(tenant_id)
                st.session_state["m023_task_list"] = tasks
                st.session_state["m023_task_tenant_id"] = tenant_id
                if "m023_claim_msg" in st.session_state:
                    del st.session_state["m023_claim_msg"]
            except Exception as exc:
                st.session_state["m023_task_error"] = str(exc)
                st.session_state.pop("m023_task_list", None)

    # 顯示錯誤
    if "m023_task_error" in st.session_state:
        st.error(f"❌ {st.session_state['m023_task_error']}")
        del st.session_state["m023_task_error"]

    # 顯示認領結果
    if "m023_claim_msg" in st.session_state:
        msg = st.session_state["m023_claim_msg"]
        if msg.get("ok"):
            st.success(f"✅ 認領成功！task_id: `{msg['task_id']}`。請前往「標注工作台」繼續。")
        else:
            st.error(f"❌ 認領失敗：{msg['error']}")

    # ── 顯示任務列表 ──────────────────────────────────────────────────────────
    task_list: list[dict] = st.session_state.get("m023_task_list", [])
    if not task_list:
        return {"mode": "idle"}

    st.divider()
    st.subheader(f"任務清單（共 {len(task_list)} 筆）")

    PAGE_SIZE = 50
    n_pages = max(1, (len(task_list) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = st.session_state.get("m023_page", 0)
    page = min(page, n_pages - 1)

    if n_pages > 1:
        col_prev, col_info, col_next = st.columns([1, 3, 1])
        with col_prev:
            if st.button("← 上一頁", disabled=page == 0, key="m023_prev"):
                st.session_state["m023_page"] = page - 1
                st.rerun()
        with col_info:
            st.caption(f"第 {page + 1} / {n_pages} 頁（共 {len(task_list)} 筆）")
        with col_next:
            if st.button("下一頁 →", disabled=page == n_pages - 1, key="m023_next"):
                st.session_state["m023_page"] = page + 1
                st.rerun()

    page_tasks = task_list[page * PAGE_SIZE: (page + 1) * PAGE_SIZE]

    for idx, task in enumerate(page_tasks):
        ant_id = task["ant_id"]
        ant_active = task.get("ant_active", 0)
        ant_period = task.get("ant_period", "")
        ext_ctx = task.get("external_context", {})
        ctx_str = str(ext_ctx)
        ctx_preview = ctx_str[:60] + "…" if len(ctx_str) > 60 else ctx_str

        icon = _ANT_ACTIVE_ICON.get(ant_active, "⚪")
        label = _ANT_ACTIVE_LABEL.get(ant_active, str(ant_active))

        col_info, col_btn = st.columns([4, 1])
        with col_info:
            st.markdown(f"{icon} **{ant_id}** — {label}")
            if ant_period:
                st.caption(f"期間：{ant_period}")
            if ctx_preview:
                st.caption(f"外部資訊：{ctx_preview}")
        with col_btn:
            if ant_active == 0:
                claim_key = f"m023_claim_{page}_{idx}"
                if st.button("✋ 認領", key=claim_key):
                    if not user_id.strip():
                        st.session_state["m023_claim_msg"] = {
                            "ok": False,
                            "error": "請先填入您的使用者 ID",
                        }
                    else:
                        try:
                            result = service.claim_task(tenant_id, ant_id, user_id.strip())
                            st.session_state["m023_claim_msg"] = {
                                "ok": True,
                                "task_id": result["task_id"],
                            }
                            # 清掉任務清單，讓使用者重新載入
                            st.session_state.pop("m023_task_list", None)
                        except Exception as exc:
                            st.session_state["m023_claim_msg"] = {
                                "ok": False,
                                "error": str(exc),
                            }
                    st.rerun()

        st.markdown("---")

    return {"mode": "idle"}
