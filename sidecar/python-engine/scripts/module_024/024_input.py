from __future__ import annotations

import base64
import importlib.util as _ilu
import json
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


def render_input() -> dict:
    _ui.inject_streamlit_zh_overrides()
    st.title("✏️ 標注工作台")
    st.caption("對已認領的任務進行標注並標記完成。")

    # 顯示上次完成任務的訊息（跨 task_id 持續顯示）
    if "m024_completion_msg" in st.session_state:
        msg = st.session_state.pop("m024_completion_msg")
        if msg.get("ok"):
            st.success(msg["text"])
        else:
            st.error(msg["text"])

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
        key="m024_selected_tenant",
    )
    tenant_id = tenant_options[selected_label]["tenant_id"]

    # ── 載入 antActive=1 的任務 ───────────────────────────────────────────────
    if st.button("🔄 重新載入任務", key="m024_refresh_tasks"):
        st.session_state.pop(f"m024_tasks_{tenant_id}", None)
        st.session_state.pop("m024_selected_task_id", None)

    if f"m024_tasks_{tenant_id}" not in st.session_state:
        try:
            tasks = service.list_tasks(tenant_id, ant_active=1)
            st.session_state[f"m024_tasks_{tenant_id}"] = tasks
        except Exception as exc:
            st.error(f"❌ 無法載入任務清單：{exc}")
            st.session_state[f"m024_tasks_{tenant_id}"] = []

    tasks: list[dict] = st.session_state.get(f"m024_tasks_{tenant_id}", [])

    if not tasks:
        st.info("目前無「標注中」任務。請至「**📋 待認領任務**」頁面認領任務後再回到此頁。")
        return {"mode": "idle"}

    # ── 任務選擇 ─────────────────────────────────────────────────────────────
    task_id_idx = {t["task_id"]: i for i, t in enumerate(tasks)}
    task_options = {
        f"{t['ant_id']} (task: {t['task_id'][:8]}…)": t["task_id"]
        for t in tasks
    }

    selected_task_label = st.selectbox(
        "選擇任務",
        options=list(task_options.keys()),
        key="m024_task_selectbox",
    )
    task_id = task_options[selected_task_label]

    # 取得任務詳情
    try:
        task = service.get_task(task_id)
    except Exception as exc:
        st.error(f"❌ 無法取得任務詳情：{exc}")
        return {"mode": "idle"}

    st.divider()

    # ── 外部 context 展示 ─────────────────────────────────────────────────────
    ext_ctx = task.get("external_context") or {}
    if ext_ctx:
        with st.expander("🔍 外部資訊 (external_context)", expanded=False):
            st.json(ext_ctx)

    # ── 圖片預覽 ──────────────────────────────────────────────────────────────
    ws_path = Path(os.environ.get("CIM_LOG_DIR", "/tmp")) / "annotation_workspace"
    img_dir = ws_path / "tasks" / task_id / "images"
    if img_dir.exists():
        img_files = (
            sorted(img_dir.glob("*.png"))
            + sorted(img_dir.glob("*.jpg"))
            + sorted(img_dir.glob("*.jpeg"))
        )
        if img_files:
            st.subheader("📷 圖片預覽")
            cols = st.columns(min(len(img_files), 3))
            for i, img_path in enumerate(img_files[:6]):  # 最多顯示 6 張
                with cols[i % 3]:
                    suffix = img_path.suffix.lower().lstrip(".")
                    mime = "jpeg" if suffix in ("jpg", "jpeg") else suffix
                    b64 = base64.b64encode(img_path.read_bytes()).decode()
                    st.markdown(
                        f'<img src="data:image/{mime};base64,{b64}" '
                        f'style="width:100%;border-radius:4px;display:block">'
                        f'<p style="text-align:center;font-size:0.8em;'
                        f'color:gray;margin-top:4px">{img_path.name}</p>',
                        unsafe_allow_html=True,
                    )
        else:
            st.warning("此任務尚無圖片，請稍後按「🔄 重新載入任務」，或聯繫管理員確認資料是否已同步。")
    else:
        st.warning("圖片尚未載入，請稍後按「🔄 重新載入任務」，或聯繫管理員確認任務資料是否已同步。")

    # ── 標注結果 ──────────────────────────────────────────────────────────────
    st.subheader("📋 標注結果")

    # 快速分類按鈕（key 含 task_id，切換任務時不殘留）
    _cls_key = f"mod024_cls_{task_id}"
    if _cls_key not in st.session_state:
        st.session_state[_cls_key] = task.get("new_classification") or ""

    st.write("**分類判定**")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("✅ OK", use_container_width=True, type="primary", key=f"m024_btn_ok_{task_id}"):
            st.session_state[_cls_key] = "OK"
    with col2:
        if st.button("❌ NG", use_container_width=True, key=f"m024_btn_ng_{task_id}"):
            st.session_state[_cls_key] = "NG"
    with col3:
        if st.button("⚠️ 待確認", use_container_width=True, key=f"m024_btn_pend_{task_id}"):
            st.session_state[_cls_key] = "待確認"

    # 顯示目前選擇
    current_cls = st.session_state[_cls_key]
    if current_cls:
        st.success(f"已選擇：{current_cls}")

    new_classification = st.text_input(
        "或手動輸入分類",
        value=current_cls,
        placeholder="OK / NG / 待確認",
        key=f"m024_new_cls_{task_id}",
    )
    # 同步手動輸入回 session_state
    if new_classification != current_cls:
        st.session_state[_cls_key] = new_classification
    current_cls = st.session_state[_cls_key]

    # ── 作業員工號（跨任務持久化，切換任務不需重填）────────────────────────────
    _worker_key = "m024_global_worker_id"
    _default_worker = (
        task.get("annotated_by")
        or st.session_state.get(_worker_key)
        or ""
    )
    annotated_by = st.text_input(
        "作業員工號",
        value=_default_worker,
        key=f"m024_annotated_by_{task_id}",
        placeholder="user001",
    )
    if annotated_by:
        st.session_state[_worker_key] = annotated_by  # 儲存供下個任務使用

    # ── 標注 JSON（進階，預設折疊） ───────────────────────────────────────────
    ann_json = task.get("annotation_json") or {}
    ann_json_str = json.dumps(ann_json, ensure_ascii=False, indent=2)

    with st.expander("🔧 進階：原始標注 JSON（技術人員用）", expanded=False):
        edited_json_str = st.text_area(
            "標注 JSON",
            value=ann_json_str,
            height=200,
            key=f"m024_ann_json_{task_id}",
        )

    st.divider()

    # ── 操作按鈕 ─────────────────────────────────────────────────────────────
    col_save, col_done, _ = st.columns([2, 2, 3])

    # 顯示上次操作結果
    msg_key = f"m024_msg_{task_id}"
    if msg_key in st.session_state:
        msg = st.session_state[msg_key]
        if msg.get("ok"):
            st.success(f"✅ {msg['text']}")
        else:
            st.error(f"❌ {msg['text']}")

    with col_save:
        if st.button("💾 儲存標注", key=f"m024_save_{task_id}"):
            try:
                parsed_json = json.loads(edited_json_str)
            except json.JSONDecodeError as exc:
                st.session_state[msg_key] = {"ok": False, "text": f"JSON 格式錯誤：{exc}"}
                st.rerun()
                return {"mode": "idle"}

            try:
                service.save_annotation(
                    task_id=task_id,
                    annotation_json=parsed_json,
                    new_classification=new_classification.strip() or None,
                    annotated_by=annotated_by.strip() or None,
                )
                st.session_state[msg_key] = {"ok": True, "text": "標注已儲存。"}
                # 清掉快取，下次重新載入
                st.session_state.pop(f"m024_tasks_{tenant_id}", None)
            except Exception as exc:
                st.session_state[msg_key] = {"ok": False, "text": f"儲存失敗：{exc}"}
            st.rerun()

    with col_done:
        if st.button("✅ 完成任務", key=f"m024_done_{task_id}"):
            if not annotated_by.strip():
                st.session_state[msg_key] = {"ok": False, "text": "請填入作業員工號後再完成任務。"}
                st.rerun()
                return {"mode": "idle"}

            try:
                result = service.complete_task(task_id=task_id, annotated_by=annotated_by.strip())
                delivery = result.get("delivery", {})
                delivery_status = delivery.get("status", "unknown")

                status_labels = {
                    "success": "✅ 結果已成功送出至 iWISC",
                    "error": "❌ 送出失敗，請通知管理員或重試",
                    "pending": "⏳ 等待送出",
                }
                display_status = status_labels.get(delivery_status, delivery_status)

                if delivery_status == "error":
                    st.session_state["m024_completion_msg"] = {
                        "ok": False,
                        "text": (
                            f"任務 {task_id[:8]}… 已標記完成（antActive→2），"
                            f"但回饋失敗：{delivery.get('error', '未知錯誤')}"
                        ),
                    }
                else:
                    st.session_state["m024_completion_msg"] = {
                        "ok": True,
                        "text": (
                            f"✅ 任務 {task_id[:8]}… 已標記完成（antActive→2）。"
                            f"回饋狀態：{display_status}"
                        ),
                    }
                st.session_state.pop(f"m024_tasks_{tenant_id}", None)
                st.session_state.pop("m024_task_selectbox", None)
            except Exception as exc:
                st.session_state[msg_key] = {"ok": False, "text": f"完成失敗：{exc}"}
            st.rerun()

    return {"mode": "idle"}
