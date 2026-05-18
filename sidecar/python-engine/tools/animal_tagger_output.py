from __future__ import annotations

import json
import os
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import streamlit as st
from streamlit_image_annotation import detection

from db_utils import SimpleDAO
from log_utils import get_logger
from tool_result import read_result
from ui_utils import show_image

log = get_logger("animal_tagger")

TOOL_ID = os.environ.get("CIM_TOOL_ID", "animal-tagger")
LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", "/tmp"))
RESULT_FILE = LOG_DIR / f"{TOOL_ID}_result.json"

LABEL_OPTIONS = ["請選擇分類", "貓", "狗", "大象", "unknown"]
ANNOTATION_LABELS = ["貓", "狗", "大象", "unknown"]

_SELECT_COLS = "id, filename, file_type, image_time, true_label, classification, tagged_at"


def _query_records(db_path: str, category_filter: str) -> list[dict]:
    dao = SimpleDAO(db_path)
    if category_filter == "ALL":
        return dao.query(f"SELECT {_SELECT_COLS} FROM images ORDER BY id")
    return dao.query(
        f"SELECT {_SELECT_COLS} FROM images WHERE true_label = ? ORDER BY id",
        (category_filter,),
    )


def _update_tag(db_path: str, record_id: int, classification: str) -> None:
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    rows = SimpleDAO(db_path).execute(
        "UPDATE images SET classification = ?, tagged_at = ? WHERE id = ?",
        (classification, now, record_id),
    )
    log.info("Tagged id=%s as %s (%d row updated)", record_id, classification, rows)


def _next_untagged_index(records: list[dict], current_idx: int) -> int:
    for offset in range(1, len(records)):
        idx = (current_idx + offset) % len(records)
        if records[idx]["classification"] is None:
            return idx
    return (current_idx + 1) % len(records)


def _ann_path(image_dir: Path, filename: str) -> Path:
    return image_dir / (Path(filename).stem + "_annotations.json")


def _load_annotations(image_dir: Path, filename: str) -> dict:
    p = _ann_path(image_dir, filename)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"bboxes": [], "labels": [], "label_list": ANNOTATION_LABELS}


def _save_annotations(image_dir: Path, filename: str, bboxes: list, labels: list) -> Path:
    data = {
        "image": filename,
        "bboxes": bboxes,
        "labels": labels,
        "label_list": ANNOTATION_LABELS,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    p = _ann_path(image_dir, filename)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _render_annotated_preview(img_path: Path, bboxes: list, labels: list) -> np.ndarray | None:
    img = cv2.imread(str(img_path))
    if img is None:
        return None
    colors = [(255, 80, 80), (80, 255, 80), (80, 80, 255), (255, 200, 0)]
    for bbox, label_id in zip(bboxes, labels):
        x, y, w, h = [int(v) for v in bbox]
        color = colors[label_id % len(colors)]
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
        label_text = ANNOTATION_LABELS[label_id] if label_id < len(ANNOTATION_LABELS) else str(label_id)
        cv2.putText(img, label_text, (x, max(y - 6, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def main() -> None:
    st.set_page_config(page_title="動物影像標記 — Output", layout="wide")
    st.title("影像標記")

    envelope = read_result(RESULT_FILE)
    if envelope is None:
        st.info("尚未載入資料，請在 Input 頁籤選擇類別並按下 ▶ 載入資料。")
        return

    ui = envelope["user_input"]
    db_path = ui["db_path"]
    image_dir = Path(ui["image_dir"])
    category_filter = ui.get("filter", "ALL")

    records = _query_records(db_path, category_filter)
    if not records:
        st.warning(f"沒有找到「{category_filter}」類別的資料。")
        return

    df = pd.DataFrame(records)
    df_display = df.rename(columns={
        "id": "ID",
        "filename": "檔名",
        "file_type": "類型",
        "image_time": "建立時間",
        "true_label": "實際類別",
        "classification": "標記分類",
        "tagged_at": "標記時間",
    })

    # ── Session state ─────────────────────────────────────────
    if "selected_idx" not in st.session_state:
        st.session_state.selected_idx = 0
    if "annotation_mode" not in st.session_state:
        st.session_state.annotation_mode = False

    total = len(records)
    tagged_count = sum(1 for r in records if r["classification"] is not None)
    ann_count = sum(1 for r in records if _ann_path(image_dir, r["filename"]).exists())
    st.caption(
        f"類別篩選：{category_filter}　｜　共 {total} 筆　｜　"
        f"已分類 {tagged_count} 筆　｜　已標注 {ann_count} 筆"
    )

    # ── Grid ──────────────────────────────────────────────────
    try:
        event = st.dataframe(
            df_display,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row",
            key="grid",
        )
        sel_rows = event.selection.rows if event.selection.rows else []
        if sel_rows:
            if st.session_state.selected_idx != sel_rows[0]:
                st.session_state.selected_idx = sel_rows[0]
                st.session_state.annotation_mode = False
    except TypeError:
        st.dataframe(df_display, use_container_width=True)
        new_idx = st.number_input(
            "選擇記錄（行號，從 0 開始）",
            min_value=0,
            max_value=total - 1,
            value=st.session_state.selected_idx,
            step=1,
        )
        if new_idx != st.session_state.selected_idx:
            st.session_state.selected_idx = new_idx
            st.session_state.annotation_mode = False

    selected_idx = int(st.session_state.selected_idx)
    selected = records[selected_idx]
    img_path = image_dir / selected["filename"]
    has_ann = _ann_path(image_dir, selected["filename"]).exists()

    st.divider()

    # ── Tagging row ───────────────────────────────────────────
    col_info, col_tag, col_submit, col_ann = st.columns([2, 2, 1, 1])
    with col_info:
        current_tag = selected["classification"] or "未標記"
        ann_badge = " ✅ 已標注" if has_ann else ""
        st.markdown(f"**選中**：`{selected['filename']}`　｜　分類：**{current_tag}**{ann_badge}")
    with col_tag:
        tag_choice = st.selectbox(
            "請選擇分類",
            LABEL_OPTIONS,
            key=f"tag_{selected['id']}",
            label_visibility="collapsed",
        )
    with col_submit:
        if st.button("Submit", type="primary", use_container_width=True):
            if tag_choice == "請選擇分類":
                st.warning("請先選擇一個分類。")
            else:
                _update_tag(db_path, selected["id"], tag_choice)
                refreshed = _query_records(db_path, category_filter)
                next_idx = _next_untagged_index(refreshed, selected_idx)
                st.session_state.selected_idx = next_idx
                st.session_state.annotation_mode = False
                st.rerun()
    with col_ann:
        ann_label = "🏷 標注中" if st.session_state.annotation_mode else "🏷 標注"
        if st.button(ann_label, use_container_width=True):
            st.session_state.annotation_mode = not st.session_state.annotation_mode
            st.rerun()

    st.divider()

    # ── Annotation mode ───────────────────────────────────────
    if st.session_state.annotation_mode:
        _render_annotation_panel(image_dir, selected, img_path)
    else:
        # ── Image preview ──────────────────────────────────────
        st.subheader(f"影像預覽：{selected['filename']}")
        if img_path.exists():
            if has_ann:
                ann_data = _load_annotations(image_dir, selected["filename"])
                preview = _render_annotated_preview(img_path, ann_data["bboxes"], ann_data["labels"])
                if preview is not None:
                    st.image(preview, use_container_width=True, caption=f"{selected['filename']}（含標注框）")
                else:
                    show_image(img_path, caption=selected["filename"])
            else:
                show_image(img_path, caption=selected["filename"])
        else:
            st.warning(f"找不到影像：{img_path}")


def _render_annotation_panel(image_dir: Path, selected: dict, img_path: Path) -> None:
    filename = selected["filename"]
    st.subheader(f"🏷 標注模式：{filename}")

    if not img_path.exists():
        st.error(f"找不到影像：{img_path}")
        return

    ann_data = _load_annotations(image_dir, filename)
    existing_bboxes: list = ann_data.get("bboxes", [])
    existing_labels: list = ann_data.get("labels", [])

    st.caption("在圖片上拖拉矩形框以新增標注，點選框後可刪除。")

    result = detection(
        image_path=str(img_path),
        label_list=ANNOTATION_LABELS,
        bboxes=existing_bboxes or [],
        labels=existing_labels or [],
        height=500,
        key=f"annotation_{filename}",
    )

    # Parse result — library returns list of {"bbox": [...], "label": int} or {"label_id": int}
    new_bboxes: list = []
    new_labels: list = []
    if result:
        for item in result:
            new_bboxes.append(item["bbox"])
            label_id = item.get("label_id", item.get("label", 0))
            new_labels.append(int(label_id))

    col_count, col_save, col_clear = st.columns([3, 1, 1])
    with col_count:
        st.caption(f"目前標注框數量：{len(new_bboxes)}")
    with col_save:
        if st.button("💾 儲存標注", type="primary", use_container_width=True):
            saved_path = _save_annotations(image_dir, filename, new_bboxes, new_labels)
            st.success(f"已儲存 {len(new_bboxes)} 個標注框 → `{saved_path.name}`")
            log.info("Saved %d annotations for %s", len(new_bboxes), filename)
    with col_clear:
        if st.button("🗑 清除全部", use_container_width=True):
            _save_annotations(image_dir, filename, [], [])
            st.session_state.annotation_mode = False
            st.rerun()

    # Show annotation summary table
    if new_bboxes:
        st.markdown("**標注清單：**")
        rows = []
        for i, (bbox, label_id) in enumerate(zip(new_bboxes, new_labels)):
            x, y, w, h = [int(v) for v in bbox]
            label_name = ANNOTATION_LABELS[label_id] if label_id < len(ANNOTATION_LABELS) else str(label_id)
            rows.append({"#": i + 1, "類別": label_name, "X": x, "Y": y, "W": w, "H": h})
        st.dataframe(rows, use_container_width=True, hide_index=True)

    # Download existing JSON if saved
    ann_file = _ann_path(image_dir, filename)
    if ann_file.exists():
        st.download_button(
            "⬇ 下載標注 JSON",
            data=ann_file.read_text(encoding="utf-8"),
            file_name=ann_file.name,
            mime="application/json",
        )


if __name__ == "__main__":
    main()
