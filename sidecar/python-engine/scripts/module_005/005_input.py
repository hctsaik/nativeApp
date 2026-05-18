from __future__ import annotations

import calendar
import os
import sqlite3
from datetime import date
from pathlib import Path

import streamlit as st


def _available_parts() -> list[str]:
    db_path = Path(os.environ.get("CIM_LOG_DIR", "/tmp")) / "edge_records.sqlite"
    if not db_path.exists():
        return []
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT parts FROM edge_records WHERE parts IS NOT NULL AND parts != '' ORDER BY parts"
        ).fetchall()
    return [r[0] for r in rows]


def _available_dates() -> list[str]:
    db_path = Path(os.environ.get("CIM_LOG_DIR", "/tmp")) / "edge_records.sqlite"
    if not db_path.exists():
        return []
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT DATE(timestamp) FROM edge_records ORDER BY 1 DESC"
        ).fetchall()
    return [r[0] for r in rows if r[0]]


def _three_months_ago(ref: date) -> date:
    month = ref.month - 3
    year = ref.year
    if month <= 0:
        month += 12
        year -= 1
    max_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(ref.day, max_day))


def render_input() -> dict:
    st.subheader(":material/manage_search: 查詢量測記錄")

    dates = _available_dates()
    if dates:
        st.info(f"資料庫中有記錄的日期：{' ｜ '.join(dates)}")
    else:
        st.info("尚無任何量測記錄，請先使用「邊緣完整度偵測」模組儲存資料。")

    today = date.today()
    default_from = _three_months_ago(today)

    col_from, col_to = st.columns(2)
    with col_from:
        date_from = st.date_input("開始日期", value=default_from, key="date_from")
    with col_to:
        date_to = st.date_input("結束日期", value=today, key="date_to")

    if date_from > date_to:
        st.warning("From 日期不能晚於 To 日期。")

    # ── 篩選條件 ──────────────────────────────────────────────────
    with st.expander("🔍 篩選條件", expanded=True):
        col_parts, col_name = st.columns(2)
        with col_parts:
            available_parts = _available_parts()
            if available_parts:
                parts_selected = st.multiselect(
                    "料號",
                    options=available_parts,
                    placeholder="留空為全部",
                    key="filter_parts",
                )
            else:
                parts_selected = []
                st.caption("（尚無料號資料）")
        with col_name:
            image_name_kw = st.text_input(
                "影像檔名（包含）",
                placeholder="留空為全部",
                key="filter_image_name",
            )

        st.markdown("**粗糙度範圍**")
        col_l1, col_l2, col_r1, col_r2 = st.columns(4)
        with col_l1:
            left_min = st.number_input("左邊 最小", value=0.0, step=0.01, format="%.3f", key="filter_left_min")
        with col_l2:
            left_max = st.number_input("左邊 最大", value=9999.0, step=0.01, format="%.3f", key="filter_left_max")
        with col_r1:
            right_min = st.number_input("右邊 最小", value=0.0, step=0.01, format="%.3f", key="filter_right_min")
        with col_r2:
            right_max = st.number_input("右邊 最大", value=9999.0, step=0.01, format="%.3f", key="filter_right_max")

    return {
        "date_from":    date_from.strftime("%Y-%m-%d"),
        "date_to":      date_to.strftime("%Y-%m-%d"),
        "parts":        parts_selected,
        "image_name_kw": image_name_kw.strip(),
        "left_min":     left_min,
        "left_max":     left_max,
        "right_min":    right_min,
        "right_max":    right_max,
    }
