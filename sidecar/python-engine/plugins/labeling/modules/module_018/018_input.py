from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_018_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_mdb_spec = _ilu.spec_from_file_location(
    "_manifest_db", _HERE.parents[3] / "scripts" / "shared" / "_manifest_db.py"
)
_mdb = _ilu.module_from_spec(_mdb_spec)
_mdb_spec.loader.exec_module(_mdb)

_help_spec = _ilu.spec_from_file_location("_help", _HERE.parents[3] / "scripts" / "shared" / "_help.py")
_help = _ilu.module_from_spec(_help_spec)
_help_spec.loader.exec_module(_help)

_FILTER_OPTIONS = ["全部", "已標注 (有 BBox)", "未標注", "已分類", "未分類"]


def render_input() -> dict:
    _help.render_help_button("module_018", "input", "🖼️ Review Gallery — 標注審查")
    st.caption("以 Grid 縮略圖 + BBox overlay 快速瀏覽標注結果")

    db_path = _cfg.get_manifest_db_path()
    manifests = _mdb.list_manifests(db_path)

    if not manifests:
        st.warning("尚未建立任何 Manifest，請先至「📥 資料來源」執行並建立資料集。")
        return {"manifest_id": ""}

    shared_id = _cfg.get_shared_manifest_id()
    manifests_list = list(manifests)
    selected = next(
        (m for m in manifests_list if m["manifest_id"] == shared_id),
        manifests_list[0],
    )
    manifest_id = selected["manifest_id"]

    st.info(
        f"📦 **{selected['name']}**　{selected.get('item_count', 0)} 張　"
        f"｜　若要切換請回 Data Feeder 重新執行"
    )

    filter_val = st.selectbox(
        "篩選條件",
        options=_FILTER_OPTIONS,
        key="m018_filter",
    )

    cols_count = st.slider("每行圖片數", min_value=2, max_value=6, value=3, key="m018_cols")

    show_overlay = st.checkbox("顯示 BBox overlay", value=True, key="m018_show_overlay")

    label_filter = st.text_input(
        "標籤篩選（留空 = 全部）",
        key="m018_label_filter",
        placeholder="例如：cat",
    ).strip()

    return {
        "manifest_id": manifest_id,
        "filter": filter_val,
        "cols_count": cols_count,
        "show_overlay": show_overlay,
        "label_filter": label_filter,
    }
