"""Output layer for the declarative-form demo (module_007)."""

from __future__ import annotations

import streamlit as st


def render_output(result: dict) -> None:
    st.subheader("宣告式表單範例 — 結果")
    if result.get("mode") != "ready":
        st.info("請在 Input 頁填表並按 ▶ 執行。")
        return
    st.caption(f"title='{result.get('title')}'　count={result.get('count')}")
    for line in result.get("lines", []):
        st.write(line)
