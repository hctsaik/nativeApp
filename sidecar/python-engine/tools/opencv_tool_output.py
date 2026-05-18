from __future__ import annotations

import base64
import os
from pathlib import Path

import numpy as np
import streamlit as st

from tool_result import read_result
from ui_utils import show_image

TOOL_ID = os.environ.get("CIM_TOOL_ID", "opencv-tool")
LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", "/tmp"))
RESULT_FILE = LOG_DIR / f"{TOOL_ID}_result.json"


def _decode_image(b64: str) -> np.ndarray:
    import cv2
    raw = base64.b64decode(b64)
    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("無法解碼影像")
    if len(img.shape) == 3 and img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
    if len(img.shape) == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return img


def main() -> None:
    st.set_page_config(page_title="OpenCV 影像處理 — Output", layout="wide")

    data = read_result(RESULT_FILE)

    if data is None:
        st.title("執行結果")
        st.info("尚未執行，請在 Input 頁籤選擇影像與功能，並按下 ▶ 執行。")
        return

    ui = data["user_input"]
    pr = data["process_result"]

    func_name = ui.get("func_name", "Unknown")
    image_label = ui.get("image_label", "")
    w = ui.get("width", 0)
    h = ui.get("height", 0)
    elapsed_ms = pr.get("elapsed_ms", 0)
    params = ui.get("params", {})

    st.title(f"執行結果：{func_name}")
    st.caption(f"影像：{image_label}　｜　尺寸：{w} × {h}　｜　耗時：{elapsed_ms} ms")

    if params:
        with st.expander("參數"):
            st.table({"參數": list(params.keys()), "值": list(params.values())})

    try:
        original = _decode_image(pr["original_b64"])
        result = _decode_image(pr["result_b64"])
    except Exception as exc:
        st.error(f"影像解碼失敗：{exc}")
        return

    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("原始影像")
        show_image(original)
    with col_right:
        st.subheader(f"處理後：{func_name}")
        show_image(result)


if __name__ == "__main__":
    main()
