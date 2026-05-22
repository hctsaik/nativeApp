from __future__ import annotations

import subprocess
from pathlib import Path

import streamlit as st


def _open_folder(path_str: str) -> None:
    try:
        target = Path(path_str)
        folder = target if target.is_dir() else target.parent
        subprocess.Popen(["explorer", str(folder)])
    except Exception:
        pass


def _path_row(label: str, path_str: str, key: str) -> None:
    col_path, col_btn = st.columns([5, 1])
    with col_path:
        st.code(path_str)
    with col_btn:
        if st.button("📂", key=key, help=f"開啟 {label}"):
            _open_folder(path_str)


def render_output(result: dict) -> None:
    mode = result.get("mode", "idle")

    if mode == "idle":
        st.info("尚未執行匯出，請在左側設定格式與目錄後按下「▶ 執行」。")
        return

    if mode == "error":
        st.error(f"匯出失敗：{result.get('error', '未知錯誤')}")
        return

    # ── 摘要 Metrics ─────────────────────────────────────────────────────────
    st.success("匯出完成！")

    total = result.get("total_items", 0)
    annotated = result.get("annotated_items", 0)
    classified = result.get("classified_items", 0)
    ann_rate = (annotated / total * 100) if total > 0 else 0.0
    clf_rate = (classified / total * 100) if total > 0 else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("總圖數", total)
    c2.metric("已標注（bbox）", annotated, f"{ann_rate:.1f}%")
    c3.metric("已分類", classified, f"{clf_rate:.1f}%")

    split_counts = result.get("split_counts", {})
    c4.metric("Train / Val / Test",
              f"{split_counts.get('train',0)} / {split_counts.get('val',0)} / {split_counts.get('test',0)}")

    st.divider()

    # ── 分布圖 ────────────────────────────────────────────────────────────────
    col_clf, col_bbox = st.columns(2)

    with col_clf:
        st.subheader("分類分布")
        clf_counts = result.get("classification_counts", {})
        if clf_counts:
            st.bar_chart(clf_counts)
        else:
            st.caption("無分類資料")

    with col_bbox:
        st.subheader("BBox 標籤分布")
        label_counts = result.get("label_counts", {})
        if label_counts:
            st.bar_chart(label_counts)
        else:
            st.caption("無 BBox 標注資料")

    st.divider()

    # ── 匯出路徑 ──────────────────────────────────────────────────────────────
    st.subheader("匯出路徑")
    export_paths: dict = result.get("export_paths", {})
    export_dir = result.get("export_dir", "")

    if export_dir:
        col_p, col_b = st.columns([5, 1])
        with col_p:
            st.caption(f"根目錄：`{export_dir}`")
        with col_b:
            if st.button("📂 根目錄", key="m014_open_root"):
                _open_folder(export_dir)

    if not export_paths:
        st.caption("無匯出路徑")
        return

    # COCO JSON
    if "coco_json" in export_paths:
        with st.expander("COCO JSON", expanded=True):
            for split_name, path_str in export_paths["coco_json"].items():
                _path_row(f"COCO {split_name}", path_str, f"m014_coco_{split_name}")

    # YOLO txt
    if "yolo_txt" in export_paths:
        with st.expander("YOLO txt", expanded=True):
            yolo = export_paths["yolo_txt"]
            if "data_yaml" in yolo:
                _path_row("data.yaml", yolo["data_yaml"], "m014_yolo_yaml")
            if "classes_txt" in yolo:
                _path_row("classes.txt", yolo["classes_txt"], "m014_yolo_classes")
            for k, v in yolo.items():
                if k not in ("data_yaml", "classes_txt"):
                    _path_row(f"images/{k}", v, f"m014_yolo_{k}")

    # Pascal VOC XML
    if "pascal_voc" in export_paths:
        with st.expander("Pascal VOC XML", expanded=True):
            voc = export_paths["pascal_voc"]
            if "annotations_dir" in voc:
                _path_row("Annotations/", voc["annotations_dir"], "m014_voc_ann")
            if "images_dir" in voc:
                _path_row("JPEGImages/", voc["images_dir"], "m014_voc_img")
            for k, v in voc.items():
                if k not in ("annotations_dir", "images_dir"):
                    _path_row(f"ImageSets/Main/{k}.txt", v, f"m014_voc_{k}")

    # ImageFolder
    if "imagefolder" in export_paths:
        with st.expander("ImageFolder（分類）", expanded=True):
            imgf = export_paths["imagefolder"]
            copied = imgf.pop("_copied", "?")
            skipped = imgf.pop("_skipped", "?")
            st.caption(f"已複製 {copied} 張，跳過 {skipped} 張（無分類標籤）")
            for split_name, path_str in imgf.items():
                _path_row(split_name, path_str, f"m014_imgf_{split_name}")

    # CSV
    if "csv" in export_paths:
        with st.expander("CSV", expanded=True):
            _path_row("annotations.csv", export_paths["csv"], "m014_csv")
