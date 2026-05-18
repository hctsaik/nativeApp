from __future__ import annotations

import base64
import os
import sqlite3
from pathlib import Path

import streamlit as st

_DB_PATH = Path(os.environ.get("CIM_LOG_DIR", "/tmp")) / "edge_records.sqlite"


def _ensure_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(_DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS edge_records (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                left_roughness        REAL,
                right_roughness       REAL,
                frequency             REAL,
                intensity             REAL,
                image_width           INTEGER,
                image_height          INTEGER,
                timestamp             TEXT,
                parts                 TEXT,
                image_name            TEXT,
                image_blob            BLOB,
                gradient_dir_variance REAL,
                psd_energy_ratio      REAL
            )
        """)
        existing = {r[1] for r in conn.execute("PRAGMA table_info(edge_records)").fetchall()}
        for col, typedef in (
            ("image_name",            "TEXT"),
            ("image_blob",            "BLOB"),
            ("gradient_dir_variance", "REAL"),
            ("psd_energy_ratio",      "REAL"),
            ("fit_overall",           "REAL"),
            ("fit_offset_score",      "REAL"),
            ("fit_left",              "REAL"),
            ("fit_right",             "REAL"),
            ("fit_avg_dist",          "REAL"),
            ("fit_avg_signed_dist",   "REAL"),
            ("fit_left_dist",         "REAL"),
            ("fit_right_dist",        "REAL"),
            ("fit_left_signed_dist",  "REAL"),
            ("fit_right_signed_dist", "REAL"),
        ):
            if col not in existing:
                conn.execute(f"ALTER TABLE edge_records ADD COLUMN {col} {typedef}")


def _signed_label(value: float | None) -> str:
    if value is None:
        return "—"
    direction = "內縮" if value > 0 else ("突出" if value < 0 else "貼齊")
    return f"{value:+.2f} px（{direction}）"


def _offset_label(value: float | None) -> str:
    if value is None:
        return "—"
    direction = "內縮" if value < 0 else ("外突" if value > 0 else "重合")
    return f"{value:+.3f}（{direction}）"


def render_output(result: dict) -> None:
    _ensure_db()

    if result.get("error") == "no_image":
        st.warning("尚未上傳影像，請在 Input 頁籤上傳後再執行。")
        return

    項目_list = []
    數值_list = []

    if result.get("fit_overall") is not None:
        項目_list += [
            "貼合偏移",
            "重合度",
            "左側貼合度",
            "右側貼合度",
            "平均偏差(px)",
            "左側偏差",
            "右側偏差",
        ]
        數值_list += [
            _offset_label(result.get("fit_offset_score")),
            result["fit_overall"],
            result["fit_left"],
            result["fit_right"],
            result.get("fit_avg_dist"),
            _signed_label(result.get("fit_left_signed_dist")),
            _signed_label(result.get("fit_right_signed_dist")),
        ]

    項目_list += [
        "影像檔名", "影像寬度", "影像長度", "現在時間", "Parts",
        "左粗糙度", "右粗糙度", "粗糙頻率", "粗糙強度",
        "梯度方向變異", "PSD 高頻能量比",
    ]
    數值_list += [
        result.get("image_name") or "（未知）",
        result["image_width"],
        result["image_height"],
        result["timestamp"],
        result["parts"] or "（未填）",
        result["left_roughness"],
        result["right_roughness"],
        result["frequency"],
        result["intensity"],
        result.get("gradient_dir_variance", "—"),
        result.get("psd_energy_ratio", "—"),
    ]

    st.table({"項目": 項目_list, "數值": 數值_list})

    if st.button("儲存此筆記錄至 SQLite", icon=":material/save:", type="primary"):
        image_blob = (
            base64.b64decode(result["image_b64"])
            if result.get("image_b64") else None
        )
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(
                """INSERT INTO edge_records
                   (left_roughness, right_roughness, frequency, intensity,
                    image_width, image_height, timestamp, parts, image_name, image_blob,
                    gradient_dir_variance, psd_energy_ratio,
                    fit_overall, fit_offset_score, fit_left, fit_right,
                    fit_avg_dist, fit_avg_signed_dist,
                    fit_left_dist, fit_right_dist,
                    fit_left_signed_dist, fit_right_signed_dist)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result["left_roughness"], result["right_roughness"],
                    result["frequency"], result["intensity"],
                    result["image_width"], result["image_height"],
                    result["timestamp"], result["parts"],
                    result.get("image_name") or "",
                    image_blob,
                    result.get("gradient_dir_variance"),
                    result.get("psd_energy_ratio"),
                    result.get("fit_overall"),
                    result.get("fit_offset_score"),
                    result.get("fit_left"),
                    result.get("fit_right"),
                    result.get("fit_avg_dist"),
                    result.get("fit_avg_signed_dist"),
                    result.get("fit_left_dist"),
                    result.get("fit_right_dist"),
                    result.get("fit_left_signed_dist"),
                    result.get("fit_right_signed_dist"),
                ),
            )
        st.toast("儲存成功！", icon=":material/check_circle:")
