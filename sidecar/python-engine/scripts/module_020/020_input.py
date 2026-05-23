from __future__ import annotations

import importlib.util as _ilu
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_020_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)


def render_input() -> dict:
    st.subheader("🗂️ 我的上傳記錄")
    st.caption("查詢透過 Sync Back 上傳至 Service 的標注批次，選取後重新下載。")

    cfg = _cfg.load_config()

    # ── Service URL（優先從 module_013 config 讀取）────────────────────────────
    default_url = cfg.get("service_url", "") or _cfg.get_service_url_from_013()
    service_url = st.text_input(
        "Service URL",
        value=st.session_state.get("m020_service_url", default_url),
        key="m020_service_url",
        placeholder="https://service.example.com",
    )
    if service_url != cfg.get("service_url", ""):
        cfg["service_url"] = service_url
        _cfg.save_config(cfg)

    st.divider()

    # ── 查詢條件 ──────────────────────────────────────────────────────────────
    st.markdown("#### 查詢條件")

    st.text_input(
        "NT Account",
        value=_cfg._NT_ACCOUNT,
        disabled=True,
        key="m020_nt_account",
    )

    col_sys, col_type = st.columns(2)
    with col_sys:
        system_name = st.selectbox(
            "系統名稱",
            options=_cfg._SYSTEM_OPTIONS,
            key="m020_system_name",
        )
    with col_type:
        data_type = st.selectbox(
            "資料類型",
            options=["全部"] + _cfg._DATA_TYPE_OPTIONS,
            key="m020_data_type",
        )

    today = date.today()
    col_from, col_to = st.columns(2)
    with col_from:
        date_from = st.date_input(
            "日期起",
            value=st.session_state.get("m020_date_from", today - timedelta(days=30)),
            key="m020_date_from",
        )
    with col_to:
        date_to = st.date_input(
            "日期迄",
            value=st.session_state.get("m020_date_to", today),
            key="m020_date_to",
        )

    return {
        "service_url": service_url,
        "nt_account": _cfg._NT_ACCOUNT,
        "system_name": system_name,
        "data_type": "" if data_type == "全部" else data_type,
        "date_from": str(date_from),
        "date_to": str(date_to),
        "submit_id": st.session_state.get("m020_selected_submit_id", ""),
    }
