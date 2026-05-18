from __future__ import annotations

"""
011_output.py — Module 011 Result Sink 輸出 UI（Streamlit）
"""

import importlib.util as _ilu
import os
import subprocess
from pathlib import Path

import streamlit as st

# ─── 動態載入 _manifest_db ────────────────────────────────────────────────────

_HERE = Path(__file__).resolve().parent
_spec = _ilu.spec_from_file_location(
    "_manifest_db", _HERE.parent / "shared" / "_manifest_db.py"
)
_mdb = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mdb)  # type: ignore[union-attr]

# ─── 路徑輔助 ─────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parents[4]  # nativeApp
_CIM_LOG_DIR = Path(
    os.environ.get("CIM_LOG_DIR", str(_PROJECT_ROOT / "tmp" / "cim_log"))
)


def _get_db_path() -> Path:
    return _CIM_LOG_DIR / "db" / "manifest.sqlite"


def _open_folder(path_str: str) -> None:
    """以系統檔案總管開啟指定資料夾。"""
    try:
        target = Path(path_str)
        folder = target if target.is_dir() else target.parent
        subprocess.Popen(["explorer", str(folder)])
    except Exception:
        pass


# ─── 主 UI ────────────────────────────────────────────────────────────────────


def render_output(result: dict) -> None:
    """
    渲染 Module 011 的輸出介面。
    result dict 由 execute_logic 回傳。
    """
    mode = result.get("mode", "idle")

    # ── Idle ─────────────────────────────────────────────────────────────────
    if mode == "idle":
        st.info("尚未執行匯出，請在左側設定參數後按下「💾 匯出」。")
        return

    # ── Error ─────────────────────────────────────────────────────────────────
    if mode == "error":
        st.error(f"匯出失敗：{result.get('error', '未知錯誤')}")
        return

    # ── Done ─────────────────────────────────────────────────────────────────
    st.success("匯出完成！")

    total_items: int = result.get("total_items", 0)
    annotation_count: int = result.get("annotation_count", 0)
    annotation_rate = (annotation_count / total_items * 100) if total_items > 0 else 0.0

    # ── 3 個 Metric ──────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    col1.metric("已標注數", annotation_count)
    col2.metric("總圖數", total_items)
    col3.metric("標注率", f"{annotation_rate:.1f}%")

    st.divider()

    # ── 標籤分布 ─────────────────────────────────────────────────────────────
    label_distribution: dict = result.get("label_distribution", {})
    st.subheader("標籤分布")
    if label_distribution:
        st.bar_chart(label_distribution)
    else:
        st.caption("無標籤資料")

    st.divider()

    # ── Split 分布 ────────────────────────────────────────────────────────────
    split_counts: dict = result.get("split_counts", {})
    st.subheader("資料分割")
    if split_counts:
        split_table = [
            {"分割集": k.capitalize(), "筆數": v}
            for k, v in split_counts.items()
        ]
        st.table(split_table)
    else:
        st.caption("無分割資料")

    st.divider()

    # ── 匯出路徑 ─────────────────────────────────────────────────────────────
    st.subheader("匯出路徑")
    export_paths: dict = result.get("export_paths", {})

    if not export_paths:
        st.caption("無匯出路徑")
    else:
        # COCO JSON
        if "coco_json" in export_paths:
            st.markdown("**COCO JSON**")
            coco_paths = export_paths["coco_json"]
            if isinstance(coco_paths, dict):
                for split_name, path_str in coco_paths.items():
                    col_path, col_btn = st.columns([5, 1])
                    with col_path:
                        st.code(path_str)
                    with col_btn:
                        if st.button(
                            "📂 開啟",
                            key=f"m011_open_coco_{split_name}",
                        ):
                            _open_folder(path_str)
            else:
                st.code(str(coco_paths))

        # YOLO txt
        if "yolo_txt" in export_paths:
            st.markdown("**YOLO txt**")
            yolo_paths = export_paths["yolo_txt"]
            if isinstance(yolo_paths, dict):
                for key, path_str in yolo_paths.items():
                    col_path, col_btn = st.columns([5, 1])
                    with col_path:
                        st.code(path_str)
                    with col_btn:
                        if st.button(
                            "📂 開啟",
                            key=f"m011_open_yolo_{key}",
                        ):
                            _open_folder(path_str)
            else:
                st.code(str(yolo_paths))

        # CSV
        if "csv" in export_paths:
            st.markdown("**CSV**")
            csv_path = export_paths["csv"]
            col_path, col_btn = st.columns([5, 1])
            with col_path:
                st.code(str(csv_path))
            with col_btn:
                if st.button("📂 開啟", key="m011_open_csv"):
                    _open_folder(str(csv_path))

    st.divider()

    # ── 匯出歷史 ─────────────────────────────────────────────────────────────
    st.subheader("匯出歷史")
    manifest_id = result.get("manifest_id", "")
    if manifest_id:
        db_path = _get_db_path()
        try:
            exports = _mdb.get_exports(db_path, manifest_id)
            if exports:
                import pandas as pd

                df = pd.DataFrame(exports)
                # 選取要顯示的欄位
                display_cols = [
                    c for c in ["run_id", "export_format", "export_path", "item_count", "created_at"]
                    if c in df.columns
                ]
                st.dataframe(df[display_cols], use_container_width=True)
            else:
                st.caption("尚無匯出記錄")
        except Exception as exc:
            st.warning(f"無法載入匯出歷史：{exc}")
    else:
        st.caption("無 manifest_id，無法查詢歷史")
