from __future__ import annotations

import importlib.util as _ilu
from datetime import datetime
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_013_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_mdb_spec = _ilu.spec_from_file_location(
    "_manifest_db", _HERE.parents[3] / "scripts" / "shared" / "_manifest_db.py"
)
_mdb = _ilu.module_from_spec(_mdb_spec)
_mdb_spec.loader.exec_module(_mdb)

_p13_spec = _ilu.spec_from_file_location("_013_process", _HERE / "013_process.py")
_p13 = _ilu.module_from_spec(_p13_spec)
_p13_spec.loader.exec_module(_p13)

_p14_spec = _ilu.spec_from_file_location(
    "_014_process", _HERE.parent / "module_014" / "014_process.py"
)
_p14 = _ilu.module_from_spec(_p14_spec)
_p14_spec.loader.exec_module(_p14)

_help_spec = _ilu.spec_from_file_location("_help", _HERE.parents[3] / "scripts" / "shared" / "_help.py")
_help = _ilu.module_from_spec(_help_spec)
_help_spec.loader.exec_module(_help)

_SYSTEM_OPTIONS = ["iWISC", "SMM"]
_DATA_TYPE_OPTIONS = ["Simulation", "Issue", "Retrain"]
_NT_ACCOUNT = "HCTSAIK"


def _load_shapes_and_clf(manifest_id: str, items: list[dict]) -> tuple[dict, dict]:
    cache_key = f"m013_shapes_{manifest_id}"
    if cache_key not in st.session_state:
        shapes_map: dict = {}
        for it in items:
            iid = it["item_id"]
            ann = _p14._load_xany_annotation(it.get("file_path", ""))
            shapes_map[iid] = _p14._parse_shapes(ann.get("shapes", []))
        st.session_state[cache_key] = shapes_map
    clf = _cfg.load_classifications(manifest_id)
    return st.session_state[cache_key], clf


def render_input() -> dict:
    _help.render_help_button("module_013", "input", "🔄 Sync Back — 同步標注結果至 Service")
    st.caption("將目前 Manifest 的標注（bbox / 分類）批次推送至遠端 Service，並附帶訓練格式壓縮檔。")

    db_path = _cfg.get_manifest_db_path()
    manifests = _mdb.list_manifests(db_path)

    _empty = {
        "manifest_id": "", "dataset_id": "", "service_url": "",
        "scope": "full", "export_format": "none",
        "system_name": "", "data_type": "", "nt_account": _NT_ACCOUNT,
        "timestamp": "", "description": "",
    }

    if not manifests:
        st.warning("尚未建立任何 Manifest，請先執行 **010 - Data Feeder**。")
        return _empty

    # ── Manifest 選擇 ─────────────────────────────────────────────────────────
    shared_id = _cfg.get_shared_manifest_id()
    manifests_list = list(manifests)
    selected = next(
        (m for m in manifests_list if m["manifest_id"] == shared_id),
        manifests_list[0],
    )
    manifest_id = selected["manifest_id"]

    st.info(
        f"📦 **{selected['name']}**　{selected.get('item_count', 0)} 張　"
        f"　｜　若要切換請回 Data Feeder 重新執行"
    )

    st.divider()

    # ── Service 設定 ──────────────────────────────────────────────────────────
    cfg = _cfg.load_config()

    service_url = st.text_input(
        "Service URL *",
        value=st.session_state.get("m013_service_url", cfg.get("service_url", "")),
        key="m013_service_url",
        placeholder="https://service.example.com",
    )
    if service_url != cfg.get("service_url", ""):
        cfg["service_url"] = service_url
        _cfg.save_config(cfg)

    st.divider()

    # ── Upload 詮釋資料 ───────────────────────────────────────────────────────
    st.markdown("#### Upload 資訊")

    col_sys, col_type = st.columns(2)
    with col_sys:
        system_name = st.selectbox(
            "系統名稱",
            options=_SYSTEM_OPTIONS,
            key="m013_system_name",
        )
    with col_type:
        data_type = st.selectbox(
            "資料類型",
            options=_DATA_TYPE_OPTIONS,
            key="m013_data_type",
        )

    # 自動組合 dataset_id：system_data_type_YYYYMMDD
    today_str = datetime.now().strftime("%Y%m%d")
    dataset_id = f"{system_name}_{data_type}_{today_str}"

    col_nt, col_ts = st.columns(2)
    with col_nt:
        st.text_input(
            "NT Account",
            value=_NT_ACCOUNT,
            disabled=True,
            key="m013_nt_account",
        )
    with col_ts:
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.text_input(
            "Timestamp",
            value=timestamp_str,
            disabled=True,
            key="m013_timestamp",
        )

    description = st.text_area(
        "Data Description",
        value=st.session_state.get("m013_description", ""),
        key="m013_description",
        placeholder="請說明此批資料的來源、用途、標注規範或其他注意事項…",
        height=120,
    )

    st.caption(f"📌 自動產生的 dataset_id：`{dataset_id}`")

    st.divider()

    # ── 送出範圍 ──────────────────────────────────────────────────────────────
    scope_opts = ["🌐 全部圖片（full）", "✅ 僅已標注（partial）"]
    scope_map = {"🌐 全部圖片（full）": "full", "✅ 僅已標注（partial）": "partial"}
    scope_label = st.radio("送出範圍", scope_opts, horizontal=True, key="m013_scope")
    scope = scope_map[scope_label]

    # ── 訓練格式 ──────────────────────────────────────────────────────────────
    fmt_opts = ["COCO JSON", "YOLO TXT", "不上傳格式包"]
    fmt_map = {"COCO JSON": "coco_json", "YOLO TXT": "yolo_txt", "不上傳格式包": "none"}
    fmt_label = st.radio("訓練格式包", fmt_opts, horizontal=True, key="m013_fmt")
    export_format = fmt_map[fmt_label]

    st.divider()

    # ── 驗證摘要 ──────────────────────────────────────────────────────────────
    items = _mdb.get_manifest_items(db_path, manifest_id)
    shapes_map, classifications = _load_shapes_and_clf(manifest_id, items)

    issues = _p13.validate_pre_sync(items, shapes_map, classifications)
    errors = [v for v in issues if v.severity == "error"]
    warnings = [v for v in issues if v.severity == "warning"]

    if scope == "partial":
        partial_count = sum(
            1 for it in items
            if shapes_map.get(it["item_id"]) or classifications.get(it["item_id"], "")
        )
        annotated_line = f"🟢 {partial_count} 張可送出（partial 模式）"
    else:
        annotated_line = f"🟢 {len(items)} 張可送出"

    with st.expander("驗證摘要", expanded=bool(errors or warnings)):
        st.markdown(annotated_line)
        for w in warnings:
            st.warning(w.message)
        for e in errors:
            st.error(e.message)

    can_submit = not errors
    if scope == "partial":
        pc = sum(
            1 for it in items
            if shapes_map.get(it["item_id"]) or classifications.get(it["item_id"], "")
        )
        if pc == 0:
            st.error("scope=partial 但無已標注項目，無法送出。")
            can_submit = False

    if not can_submit:
        st.button("🚀 送出至 Service", disabled=True, use_container_width=True)

    return {
        "manifest_id": manifest_id,
        "dataset_id": dataset_id,
        "service_url": service_url,
        "scope": scope,
        "export_format": export_format,
        "system_name": system_name,
        "data_type": data_type,
        "nt_account": _NT_ACCOUNT,
        "timestamp": timestamp_str,
        "description": description,
    }
