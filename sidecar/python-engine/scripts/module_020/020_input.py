from __future__ import annotations

import importlib.util as _ilu
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_020_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_help_spec = _ilu.spec_from_file_location("_help", _HERE.parent / "shared" / "_help.py")
_help = _ilu.module_from_spec(_help_spec)
_help_spec.loader.exec_module(_help)


def render_input() -> dict:
    _help.render_help_button("module_020", "input", "📥 Download")
    st.caption("查詢透過 Sync Back 上傳至 Service 的標注批次，選取後重新下載。")
    st.caption("標示 `*` 為必填，其餘為選填。")

    cfg = _cfg.load_config()

    # ── Service URL（必填）────────────────────────────────────────────────────
    default_url = cfg.get("service_url", "") or _cfg.get_service_url_from_013()
    service_url = st.text_input(
        "Service URL *",
        value=st.session_state.get("m020_service_url", default_url),
        key="m020_service_url",
        placeholder="https://service.example.com",
    )
    if service_url != cfg.get("service_url", ""):
        cfg["service_url"] = service_url
        _cfg.save_config(cfg)

    if not service_url.strip():
        st.caption("⚠️ 請填寫 Service URL 才能查詢。")

    st.divider()

    # ── 查詢條件 ──────────────────────────────────────────────────────────────
    st.markdown("#### 查詢條件")

    # NT Account（選填）
    nt_account = st.text_input(
        "NT Account（選填）",
        value=st.session_state.get("m020_nt_account", ""),
        key="m020_nt_account",
        placeholder="例：HCTSAIK",
        help="留空將查詢所有人的記錄（管理員模式）。",
    )
    if not nt_account.strip():
        st.warning("未填 NT Account，將查詢所有人的記錄。", icon="⚠️")

    col_sys, col_type = st.columns(2)
    with col_sys:
        # 系統名稱（選填，但建議填）
        system_name = st.selectbox(
            "系統名稱（選填）",
            options=["全部"] + _cfg._SYSTEM_OPTIONS,
            key="m020_system_name",
            help="建議選擇以縮小查詢範圍。",
        )
    with col_type:
        data_type = st.selectbox(
            "資料類型（選填）",
            options=["全部"] + _cfg._DATA_TYPE_OPTIONS,
            key="m020_data_type",
        )

    # 日期區間（必填）
    today = date.today()
    st.markdown("**日期區間 \***")
    col_from, col_to = st.columns(2)
    with col_from:
        date_from = st.date_input(
            "起始日期",
            value=st.session_state.get("m020_date_from", today - timedelta(days=30)),
            key="m020_date_from",
        )
    with col_to:
        date_to = st.date_input(
            "結束日期",
            value=st.session_state.get("m020_date_to", today),
            key="m020_date_to",
        )

    if date_from > date_to:
        st.error("起始日期不能晚於結束日期。")

    return {
        "service_url": service_url,
        "nt_account": nt_account.strip(),
        "system_name": "" if system_name == "全部" else system_name,
        "data_type": "" if data_type == "全部" else data_type,
        "date_from": str(date_from),
        "date_to": str(date_to),
        "submit_id": st.session_state.get("m020_selected_submit_id", ""),
    }
