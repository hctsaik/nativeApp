from __future__ import annotations

from pathlib import Path

import streamlit as st

_TOOLS_DIR = Path(__file__).resolve().parent.parent.parent / "tools"
_DEFAULT_IMAGE = _TOOLS_DIR / "road.png"


def render_input() -> dict:
    st.subheader("影像來源")
    st.image(str(_DEFAULT_IMAGE), caption="road.png（固定測試圖片）", use_container_width=True)

    memo = st.text_input("Memo / 備註", placeholder="輸入任意備註文字…")

    return {
        "image_path": str(_DEFAULT_IMAGE),
        "memo": memo,
    }
