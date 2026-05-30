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
    st.title("📊 完成報表 — 統計圖表")
    st.caption("各 Tenant 的標注進度橫條圖與最近完成任務列表。")

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
        key="m025_out_selected_tenant",
    )
    tenant_id = tenant_options[selected_label]["tenant_id"]

    if st.button("🔄 重新整理", key="m025_out_refresh"):
        st.session_state.pop(f"m025_out_stats_{tenant_id}", None)
        st.session_state.pop(f"m025_out_recent_{tenant_id}", None)

    # 統計資料
    if f"m025_out_stats_{tenant_id}" not in st.session_state:
        try:
            st.session_state[f"m025_out_stats_{tenant_id}"] = service.get_dashboard_stats(tenant_id)
        except Exception as exc:
            st.error(f"❌ 無法取得統計：{exc}")
            st.session_state[f"m025_out_stats_{tenant_id}"] = None

    stats = st.session_state.get(f"m025_out_stats_{tenant_id}")

    if stats:
        st.subheader("任務狀態分佈")
        total = max(stats.get("total", 1), 1)
        pending = stats.get("pending", 0)
        processing = stats.get("processing", 0)
        completed = stats.get("completed", 0)

        # 橫條圖（用 Streamlit progress bar 模擬）
        st.write("**⚪ 待標注**")
        st.progress(pending / total if total else 0)
        st.caption(f"{pending} / {total} 筆")

        st.write("**🟠 標注中**")
        st.progress(processing / total if total else 0)
        st.caption(f"{processing} / {total} 筆")

        st.write("**🟢 已完成**")
        st.progress(completed / total if total else 0)
        st.caption(f"{completed} / {total} 筆")

    st.divider()

    # 最近完成任務（最新 10 筆）
    st.subheader("最近完成任務（最新 10 筆）")

    if f"m025_out_recent_{tenant_id}" not in st.session_state:
        try:
            all_completed = service.list_tasks(tenant_id, ant_active=2)
            # 依 updated_at 降序排列，取前 10
            sorted_tasks = sorted(
                all_completed,
                key=lambda t: t.get("updated_at") or "",
                reverse=True,
            )[:10]
            st.session_state[f"m025_out_recent_{tenant_id}"] = sorted_tasks
        except Exception as exc:
            st.error(f"❌ 無法載入已完成任務：{exc}")
            st.session_state[f"m025_out_recent_{tenant_id}"] = []

    recent_tasks: list[dict] = st.session_state.get(f"m025_out_recent_{tenant_id}", [])

    if not recent_tasks:
        st.info("目前無已完成任務。")
        return

    for task in recent_tasks:
        col1, col2, col3 = st.columns([2, 2, 3])
        col1.markdown(f"🟢 **{task.get('ant_id', '—')}**")
        col2.caption(f"標注：`{task.get('annotated_by') or '—'}`")
        col3.caption(f"{task.get('updated_at', '—')}")
