from __future__ import annotations

import streamlit as st


def render_output(result: dict) -> None:
    w, h = result["resolution"]
    size_bytes = result["file_size_bytes"]
    size_kb = result["file_size_kb"]

    st.table({
        "欄位": ["檔案名稱", "解析度", "檔案大小", "Memo"],
        "值": [
            result["filename"],
            f"{w} × {h}",
            f"{size_bytes:,} bytes（{size_kb} KB）",
            result["memo"] or "（無）",
        ],
    })
