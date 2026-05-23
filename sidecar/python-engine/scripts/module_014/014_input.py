from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_014_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_mdb_spec = _ilu.spec_from_file_location(
    "_manifest_db", _HERE.parent / "shared" / "_manifest_db.py"
)
_mdb = _ilu.module_from_spec(_mdb_spec)
_mdb_spec.loader.exec_module(_mdb)

_help_spec = _ilu.spec_from_file_location("_help", _HERE.parent / "shared" / "_help.py")
_help = _ilu.module_from_spec(_help_spec)
_help_spec.loader.exec_module(_help)

_FORMAT_MAP = {
    "COCO JSON（Detection）": "coco_json",
    "YOLO txt（Detection）": "yolo_txt",
    "Pascal VOC XML（Detection）": "pascal_voc",
    "ImageFolder（Classification）": "imagefolder",
    "CSV（Flat）": "csv",
}


def _browse_directory() -> str:
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


def render_input() -> dict:
    st.subheader("📤 Export — 多格式標注匯出")
    st.caption("將標注結果匯出為各種 ML 訓練框架所需格式。")
    _help.render_help_button("module_014", "input")

    db_path = _cfg.get_manifest_db_path()
    manifests = _mdb.list_manifests(db_path)

    if not manifests:
        st.warning("尚未建立任何 Manifest，請先執行 **010 - Data Feeder**。")
        return {
            "manifest_id": "",
            "export_formats": [],
            "export_dir": "",
            "split_train": 70,
            "split_val": 15,
            "split_test": 15,
            "stratified": True,
        }

    # ── 自動使用 shared manifest（與 Data Feeder 同步） ──────────────────────
    shared_id = _cfg.get_shared_manifest_id()
    manifests_list = list(manifests)
    selected = next(
        (m for m in manifests_list if m["manifest_id"] == shared_id),
        manifests_list[0],
    )
    manifest_id = selected["manifest_id"]

    clf = _cfg.load_classifications(manifest_id)
    clf_count = len(clf)
    col1, col2 = st.columns(2)
    col1.metric("圖片數", selected.get("item_count", 0))
    col2.metric("已分類數", clf_count, help="module_012 分類結果（ImageFolder 格式需要）")
    st.info(
        f"📦 **{selected['name']}**　｜　若要切換請回 Data Feeder 重新執行"
    )

    st.divider()

    # ── 匯出格式 ────────────────────────────────────────────────────────────
    st.subheader("1. 匯出格式")

    cfg = _cfg.load_config()
    saved_formats = cfg.get("default_export_formats", ["coco_json"])
    default_display = [k for k, v in _FORMAT_MAP.items() if v in saved_formats]

    selected_display = st.multiselect(
        "選擇要匯出的格式（可複選）",
        options=list(_FORMAT_MAP.keys()),
        default=default_display or ["COCO JSON（Detection）"],
        key="m014_formats",
    )
    export_formats = [_FORMAT_MAP[f] for f in selected_display]

    # 格式說明
    with st.expander("格式說明", expanded=False):
        st.markdown("""
| 格式 | 用途 | 需要 |
|------|------|------|
| **COCO JSON** | Detectron2、MMDetection、PyTorch | bbox 標注（X-AnyLabeling） |
| **YOLO txt** | YOLOv5/v8/v11 | bbox 標注（X-AnyLabeling） |
| **Pascal VOC XML** | Faster R-CNN、TF Object Detection API | bbox 標注（X-AnyLabeling） |
| **ImageFolder** | PyTorch `ImageFolder`、Keras `image_dataset_from_directory` | 分類標籤（module_012） |
| **CSV** | 通用分析、自訂訓練腳本 | bbox 或分類（任一） |
""")

    st.divider()

    # ── 資料分割（可選） ────────────────────────────────────────────────────
    st.subheader("2. Train / Val / Test 分割")

    enable_split = st.checkbox(
        "啟用 Train / Val / Test 分割",
        value=cfg.get("enable_split", False),
        key="m014_enable_split",
    )

    if enable_split:
        col_tr, col_va, col_te = st.columns(3)
        with col_tr:
            split_train = st.number_input("Train (%)", 0, 100,
                                          value=cfg.get("split_train", 70), step=5,
                                          key="m014_split_train")
        with col_va:
            split_val = st.number_input("Val (%)", 0, 100,
                                        value=cfg.get("split_val", 15), step=5,
                                        key="m014_split_val")
        with col_te:
            split_test = st.number_input("Test (%)", 0, 100,
                                         value=cfg.get("split_test", 15), step=5,
                                         key="m014_split_test")

        total_pct = int(split_train) + int(split_val) + int(split_test)
        if total_pct != 100:
            st.warning(f"加總 {total_pct}%，執行時會自動正規化")
        else:
            st.success("加總 100% ✓")

        stratified = st.checkbox(
            "Stratified Split（依分類標籤均勻分配）",
            value=cfg.get("stratified_split", True),
            key="m014_stratified",
        )
    else:
        st.caption("停用分割時，所有圖片匯出至同一個目錄（不建立 train/val/test 子資料夾）。")
        split_train, split_val, split_test, stratified = 100, 0, 0, False

    st.divider()

    # ── 匯出目錄 ────────────────────────────────────────────────────────────
    st.subheader("3. 匯出目錄")

    default_dir = str(_cfg.get_default_export_dir(manifest_id))
    col_dir, col_btn = st.columns([4, 1])
    with col_dir:
        export_dir = st.text_input(
            "匯出根目錄",
            value=st.session_state.get("m014_export_dir", default_dir),
            key="m014_export_dir",
            placeholder=default_dir,
        )
    with col_btn:
        st.write("")
        if st.button("📂 瀏覽", key="m014_browse"):
            chosen = _browse_directory()
            if chosen:
                st.session_state["m014_export_dir"] = chosen
                st.rerun()

    # 儲存設定
    try:
        cfg["default_export_formats"] = export_formats
        cfg["enable_split"] = enable_split
        cfg["split_train"] = int(split_train)
        cfg["split_val"] = int(split_val)
        cfg["split_test"] = int(split_test)
        cfg["stratified_split"] = stratified
        _cfg.save_config(cfg)
    except Exception:
        pass

    return {
        "manifest_id": manifest_id,
        "export_formats": export_formats,
        "export_dir": export_dir,
        "enable_split": enable_split,
        "split_train": int(split_train),
        "split_val": int(split_val),
        "split_test": int(split_test),
        "stratified": stratified,
    }
