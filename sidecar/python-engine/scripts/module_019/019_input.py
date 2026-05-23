from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_019_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_proc_spec = _ilu.spec_from_file_location("_019_process", _HERE / "019_process.py")
_proc = _ilu.module_from_spec(_proc_spec)
_proc_spec.loader.exec_module(_proc)

_help_spec = _ilu.spec_from_file_location("_help", _HERE.parent / "shared" / "_help.py")
_help = _ilu.module_from_spec(_help_spec)
_help_spec.loader.exec_module(_help)


def render_input() -> dict:
    st.subheader("🌐 Data Downloader — 從遠端服務取得資料集")
    st.caption("打 Service 下載資料包（ZIP），解壓後交由 Data Feeder 建立 Manifest。")
    _help.render_help_button("module_019", "input")

    cfg = _cfg.load_config()

    # ── Service URL ────────────────────────────────────────────────────────────
    st.subheader("1. Service 設定")

    if "m019_service_url" not in st.session_state:
        st.session_state["m019_service_url"] = cfg.get("service_url", "")

    service_url = st.text_input(
        "Service Base URL",
        key="m019_service_url",
        placeholder="http://api.internal:8080",
    )

    if service_url != cfg.get("service_url", ""):
        cfg["service_url"] = service_url
        _cfg.save_config(cfg)
        # 清掉資料集選擇，讓使用者重新載入
        st.session_state.pop("m019_datasets", None)
        st.session_state.pop("m019_dataset_id", None)

    st.divider()

    # ── 資料集選擇 ─────────────────────────────────────────────────────────────
    st.subheader("2. 選擇資料集")

    if not service_url:
        st.info("請先填入 Service Base URL。")
        return {"service_url": "", "dataset_id": "", "dataset_name": "", "overwrite": False}

    col_refresh, _ = st.columns([1, 4])
    with col_refresh:
        if st.button("🔄 載入資料集清單", key="m019_refresh_datasets"):
            st.session_state.pop("m019_datasets", None)

    datasets: list[dict] = st.session_state.get("m019_datasets", [])
    dataset_error = ""

    if not datasets:
        with st.spinner("取得資料集清單…"):
            try:
                datasets = _proc.list_datasets(service_url)
                st.session_state["m019_datasets"] = datasets
            except Exception as exc:
                dataset_error = str(exc)

    if dataset_error:
        st.error(f"❌ {dataset_error}")
        return {"service_url": service_url, "dataset_id": "", "dataset_name": "", "overwrite": False}

    if not datasets:
        st.warning("此 Service 目前沒有可用的資料集。")
        return {"service_url": service_url, "dataset_id": "", "dataset_name": "", "overwrite": False}

    dataset_options = {f"{d['name']} ({d.get('item_count', '?')} 張)": d for d in datasets}
    last_name = cfg.get("last_dataset_name", "")
    default_key = next(
        (k for k in dataset_options if dataset_options[k].get("dataset_id") == cfg.get("last_dataset_id", "")),
        list(dataset_options.keys())[0],
    )

    selected_label = st.selectbox(
        "資料集",
        options=list(dataset_options.keys()),
        index=list(dataset_options.keys()).index(default_key),
        key="m019_dataset_select",
    )
    selected = dataset_options[selected_label]
    dataset_id = selected["dataset_id"]
    dataset_name = selected["name"]

    if selected.get("description"):
        st.caption(selected["description"])

    # 儲存最後選擇
    cfg["last_dataset_id"] = dataset_id
    cfg["last_dataset_name"] = dataset_name
    _cfg.save_config(cfg)

    st.divider()

    # ── 下載選項 ───────────────────────────────────────────────────────────────
    st.subheader("3. 下載選項")

    # 顯示已有的 cache
    downloads_dir = _cfg.get_downloads_dir()
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in dataset_name) or dataset_id
    existing = sorted(downloads_dir.glob(f"{safe_name}_*"), reverse=True)

    overwrite = False
    if existing:
        latest = existing[0]
        st.success(f"✅ 已有下載紀錄：`{latest.name}`")
        overwrite = st.checkbox(
            "重新下載（覆蓋現有資料，重新取得最新版本）",
            value=False,
            key="m019_overwrite",
        )
        if not overwrite:
            st.info("不勾選將直接使用現有資料夾，不重新下載。")
    else:
        st.info(f"此資料集尚未下載，按「執行」開始下載。")

    return {
        "service_url": service_url,
        "dataset_id": dataset_id,
        "dataset_name": dataset_name,
        "overwrite": overwrite,
    }
