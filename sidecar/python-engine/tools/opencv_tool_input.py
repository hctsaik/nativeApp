from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import streamlit as st

from opencv_tool import (
    FUNCTIONS,
    _DEFAULT_IMAGE,
    _bgr_to_display,
    _host_image_paths,
    _load_bgr,
    _process,
    _sidebar_params,
)
from tool_comms import notify_complete, notify_start
from tool_result import write_result
from ui_utils import show_image

TOOL_ID = os.environ.get("CIM_TOOL_ID", "opencv-tool")
LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", "/tmp"))
RESULT_FILE = LOG_DIR / f"{TOOL_ID}_result.json"


def _encode_image(image: np.ndarray) -> str:
    rgb = _bgr_to_display(image)
    _, buf = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    return base64.b64encode(buf.tobytes()).decode("ascii")


def main() -> None:
    st.set_page_config(page_title="OpenCV 影像處理 — Input", layout="wide")

    # ── Image source ──────────────────────────────────────────────
    st.sidebar.header("影像來源")
    host_paths = _host_image_paths()

    source_options = ["預設影像（road.png）"]
    if host_paths:
        source_options = [f"Host 選擇：{Path(p).name}" for p in host_paths] + source_options
    source_options.append("上傳圖片")

    source_choice = st.sidebar.selectbox("選擇來源", source_options)

    image_bgr: Optional[np.ndarray] = None
    image_path_label = "road.png"

    if source_choice.startswith("Host 選擇："):
        idx = [f"Host 選擇：{Path(p).name}" for p in host_paths].index(source_choice)
        image_bgr = _load_bgr(host_paths[idx])
        image_path_label = Path(host_paths[idx]).name
        if image_bgr is None:
            st.sidebar.error("無法讀取 Host 選擇的圖片")

    elif source_choice == "上傳圖片":
        uploaded = st.sidebar.file_uploader("選擇圖片", type=["png", "jpg", "jpeg", "bmp"])
        if uploaded is not None:
            file_bytes = np.frombuffer(uploaded.read(), np.uint8)
            image_bgr = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            image_path_label = uploaded.name

    if image_bgr is None:
        image_bgr = _load_bgr(_DEFAULT_IMAGE)

    if image_bgr is None:
        st.error("無法載入影像，請確認 road.png 存在於工具目錄。")
        st.stop()

    # ── Function + params ─────────────────────────────────────────
    st.sidebar.divider()
    st.sidebar.header("處理功能")
    func_name = st.sidebar.selectbox("選擇功能", FUNCTIONS)
    params = _sidebar_params(func_name)
    # ── Execute button at top of main area ───────────────────────
    h, w = image_bgr.shape[:2]
    top_left, top_right = st.columns([4, 1])
    with top_left:
        st.caption(f"影像：{image_path_label}　｜　尺寸：{w} × {h} 像素　｜　功能：{func_name}")
    with top_right:
        execute_clicked = st.button("▶ 執行", type="primary", use_container_width=True)

    # ── Preview original ──────────────────────────────────────────
    st.subheader("原始影像預覽")
    show_image(_bgr_to_display(image_bgr))

    # ── Execute ───────────────────────────────────────────────────
    if execute_clicked:
        notify_start()
        with st.spinner("運算中…"):
            try:
                t0 = time.perf_counter()
                result_img = _process(image_bgr, func_name, params)
                elapsed_ms = (time.perf_counter() - t0) * 1000

                user_input = {
                    "func_name": func_name,
                    "image_label": image_path_label,
                    "width": w,
                    "height": h,
                    "params": {k: str(v) for k, v in params.items()},
                }
                process_result = {
                    "original_b64": _encode_image(image_bgr),
                    "result_b64": _encode_image(result_img),
                    "elapsed_ms": round(elapsed_ms, 1),
                }
                write_result(RESULT_FILE, user_input, process_result)
                notify_complete()
                st.success("執行完成，請切換至 Output 頁籤查看結果。")
            except Exception as exc:
                notify_complete(success=False, error=str(exc))
                st.error(f"執行失敗：{exc}")


if __name__ == "__main__":
    main()
