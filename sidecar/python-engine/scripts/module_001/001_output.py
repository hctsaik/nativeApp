from __future__ import annotations

import cv2
import numpy as np
import streamlit as st


def _to_rgb(image: np.ndarray) -> np.ndarray:
    if len(image.shape) == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def render_output(result: dict) -> None:
    func_name: str = result["func_name"]
    elapsed_ms: float = result["elapsed_ms"]
    w, h = result["size"]

    st.caption(f"尺寸：{w} × {h} 像素　｜　處理耗時：{elapsed_ms:.1f} ms")

    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("原始影像")
        st.image(_to_rgb(result["original_bgr"]), use_container_width=True)
    with col_right:
        st.subheader(f"處理後：{func_name}")
        st.image(_to_rgb(result["result_bgr"]), use_container_width=True)
