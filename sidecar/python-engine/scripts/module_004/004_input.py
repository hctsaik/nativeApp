from __future__ import annotations

import streamlit as st


def render_input() -> dict:
    st.subheader(":material/upload: 影像來源")
    uploaded = st.file_uploader("上傳影像", type=["png", "jpg", "jpeg", "bmp"])
    image_bytes = uploaded.read() if uploaded is not None else None
    image_name = uploaded.name if uploaded is not None else ""

    col1, col2 = st.columns([1, 4])
    with col1:
        st.markdown(":material/tag: **Parts**")
    with col2:
        parts = st.text_input("parts_input", label_visibility="collapsed", placeholder="輸入 Parts 編號或說明")

    enable_fit_score = st.checkbox(
        "啟用藍框貼合度分析",
        value=True,
        help="輸出 0～1 的貼合度；1.00 表示黑邊與藍框貼齊，0.00 表示偏差超過約 20px。",
    )

    return {
        "image_bytes":      image_bytes,
        "image_name":       image_name,
        "parts":            parts,
        "enable_fit_score": enable_fit_score,
    }
