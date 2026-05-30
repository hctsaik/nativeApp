from __future__ import annotations

"""
011_input.py — Module 011 Result Sink 輸入 UI（Streamlit）
"""

import importlib.util as _ilu
import os
from pathlib import Path

import streamlit as st

# ─── 動態載入 _manifest_db ────────────────────────────────────────────────────

_HERE = Path(__file__).resolve().parent
_spec = _ilu.spec_from_file_location(
    "_manifest_db", _HERE.parents[3] / "scripts" / "shared" / "_manifest_db.py"
)
_mdb = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mdb)  # type: ignore[union-attr]

# ─── 路徑輔助 ─────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parents[6]  # nativeApp
_CIM_LOG_DIR = Path(
    os.environ.get("CIM_LOG_DIR", str(_PROJECT_ROOT / "tmp" / "cim_log"))
)

_FORMAT_MAP = {
    "COCO JSON": "coco_json",
    "YOLO txt": "yolo_txt",
    "CSV": "csv",
}


def _get_db_path() -> Path:
    return _CIM_LOG_DIR / "db" / "manifest.sqlite"


def _browse_directory() -> str:
    """使用 tkinter 開啟目錄選擇對話框。"""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", True)
        folder = filedialog.askdirectory(title="選擇匯出目錄")
        root.destroy()
        return folder or ""
    except Exception:
        return ""


# ─── 主 UI ────────────────────────────────────────────────────────────────────


def render_input() -> dict:
    """
    渲染 Module 011 的輸入介面，回傳 execute_logic 所需的 params dict。
    """
    st.header("💾 Result Sink — 標注結果儲存與匯出")

    db_path = _get_db_path()

    # ── Section 1：選擇 Manifest ──────────────────────────────────────────────
    st.subheader("1. 選擇 Manifest")

    manifests = _mdb.list_manifests(db_path)

    if not manifests:
        st.warning("目前沒有任何 Manifest，請先執行 Module 008 建立資料集。")
        return {
            "manifest_id": "",
            "run_id": "",
            "export_formats": [],
            "export_dir": "",
            "split_train": 70,
            "split_val": 15,
            "split_test": 15,
            "stratified": True,
        }

    # 建立顯示選項
    manifest_options = [
        f"{m['name']} ({m.get('item_count', 0)} 筆) — {m['manifest_id']}"
        for m in manifests
    ]

    selected_idx = st.selectbox(
        "選擇 Manifest",
        options=range(len(manifest_options)),
        format_func=lambda i: manifest_options[i],
        key="m011_manifest_idx",
    )

    selected_manifest = manifests[selected_idx]
    manifest_id = selected_manifest["manifest_id"]

    # 顯示 manifest 摘要
    with st.expander("Manifest 摘要", expanded=True):
        col1, col2, col3 = st.columns(3)
        col1.metric("來源類型", selected_manifest.get("source_type", "—"))
        col2.metric("建立時間", selected_manifest.get("created_at", "—")[:10])
        col3.metric("圖片數", selected_manifest.get("item_count", 0))

    st.divider()

    # ── Section 2：Run ID ─────────────────────────────────────────────────────
    st.subheader("2. Run ID")

    run_id_input = st.text_input(
        "Run ID（留空自動新建）",
        key="m011_run_id",
        placeholder="留空則自動產生",
    )

    run_id = run_id_input.strip()

    if run_id:
        existing_results = _mdb.get_annotation_results(db_path, run_id)
        st.info(f"已找到 Run ID `{run_id}`，現有標注數：**{len(existing_results)}** 筆")
    else:
        st.caption("留空將在執行時自動產生新的 Run ID（UUID）")

    st.divider()

    # ── Section 3：匯出設定 ───────────────────────────────────────────────────
    st.subheader("3. 匯出設定")

    # 匯出格式
    selected_formats_display = st.multiselect(
        "匯出格式",
        options=list(_FORMAT_MAP.keys()),
        default=["COCO JSON"],
        key="m011_export_formats",
    )
    export_formats = [_FORMAT_MAP[f] for f in selected_formats_display]

    # 匯出目錄
    col_dir, col_btn = st.columns([4, 1])
    with col_dir:
        export_dir = st.text_input(
            "匯出目錄（留空使用預設路徑）",
            key="m011_export_dir",
            placeholder=str(_CIM_LOG_DIR / "exports" / "<run_id>"),
        )
    with col_btn:
        st.write("")  # 空行對齊
        if st.button("📂 瀏覽", key="m011_browse_dir"):
            chosen = _browse_directory()
            if chosen:
                st.session_state["m011_export_dir"] = chosen
                st.rerun()

    # Train/Val/Test 分割
    st.markdown("**資料分割比例**")
    col_tr, col_va, col_te = st.columns(3)
    with col_tr:
        split_train = st.number_input(
            "Train (%)",
            min_value=0,
            max_value=100,
            value=70,
            step=5,
            key="m011_split_train",
        )
    with col_va:
        split_val = st.number_input(
            "Val (%)",
            min_value=0,
            max_value=100,
            value=15,
            step=5,
            key="m011_split_val",
        )
    with col_te:
        split_test = st.number_input(
            "Test (%)",
            min_value=0,
            max_value=100,
            value=15,
            step=5,
            key="m011_split_test",
        )

    total_pct = int(split_train) + int(split_val) + int(split_test)
    if total_pct != 100:
        st.warning(f"分割比例加總為 {total_pct}%，建議調整至 100%（執行時將自動正規化）")
    else:
        st.success("分割比例加總：100% ✓")

    # Stratified Split
    stratified = st.checkbox(
        "使用 Stratified Split（依標籤類別均勻分配）",
        value=True,
        key="m011_stratified",
    )

    st.divider()

    # ── 主按鈕 ────────────────────────────────────────────────────────────────
    st.button("💾 匯出", key="m011_export_btn", type="primary")

    return {
        "manifest_id": manifest_id,
        "run_id": run_id,
        "export_formats": export_formats,
        "export_dir": export_dir,
        "split_train": int(split_train),
        "split_val": int(split_val),
        "split_test": int(split_test),
        "stratified": stratified,
    }
