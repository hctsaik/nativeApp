from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import streamlit as st

_TOOLS_DIR = Path(__file__).resolve().parent.parent.parent / "tools"
_DEFAULT_IMAGE = _TOOLS_DIR / "road.png"

FUNCTIONS = [
    "原始影像",
    "灰階轉換",
    "高斯模糊",
    "Canny 邊緣偵測",
    "二值化",
    "侵蝕",
    "膨脹",
    "銳化",
    "Sobel 邊緣",
    "直方圖均衡化",
    "輪廓偵測",
]


def _host_image_paths() -> list[str]:
    path_file = os.environ.get("CIM_SELECTED_PATHS_FILE")
    if not path_file:
        return []
    try:
        data = json.loads(Path(path_file).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    exts = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}
    return [p for p in data.get("paths", []) if Path(p).suffix.lower() in exts]


def _load_bgr(path: Path | str) -> Optional[np.ndarray]:
    return cv2.imread(str(path))


def render_input() -> dict:
    st.sidebar.header("影像來源")
    host_paths = _host_image_paths()

    source_options = ["預設影像（road.png）"]
    if host_paths:
        source_options = [f"Host 選擇：{Path(p).name}" for p in host_paths] + source_options
    source_options.append("上傳圖片")

    source_choice = st.sidebar.selectbox("選擇來源", source_options)

    image_bgr: Optional[np.ndarray] = None

    if source_choice.startswith("Host 選擇："):
        idx = [f"Host 選擇：{Path(p).name}" for p in host_paths].index(source_choice)
        image_bgr = _load_bgr(host_paths[idx])
        if image_bgr is None:
            st.sidebar.error("無法讀取 Host 選擇的圖片")

    elif source_choice == "上傳圖片":
        uploaded = st.sidebar.file_uploader("選擇圖片", type=["png", "jpg", "jpeg", "bmp"])
        if uploaded is not None:
            file_bytes = np.frombuffer(uploaded.read(), np.uint8)
            image_bgr = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

    if image_bgr is None:
        image_bgr = _load_bgr(_DEFAULT_IMAGE)

    if image_bgr is None:
        st.error("無法載入影像，請確認 road.png 存在於工具目錄。")
        st.stop()

    st.sidebar.divider()
    st.sidebar.header("處理功能")
    func_name = st.sidebar.selectbox("選擇功能", FUNCTIONS)

    params: dict = {}
    if func_name == "高斯模糊":
        params["kernel_size"] = st.sidebar.slider("Kernel Size（奇數）", 1, 31, 5, step=2)
        params["sigma"] = st.sidebar.slider("Sigma", 0.0, 10.0, 1.0, step=0.1)

    elif func_name == "Canny 邊緣偵測":
        params["threshold1"] = st.sidebar.slider("Threshold 1（低閾值）", 0, 255, 50)
        params["threshold2"] = st.sidebar.slider("Threshold 2（高閾值）", 0, 255, 150)

    elif func_name == "二值化":
        params["use_otsu"] = st.sidebar.checkbox("使用 Otsu 自動閾值", value=False)
        params["value"] = 0 if params["use_otsu"] else st.sidebar.slider("閾值", 0, 255, 127)

    elif func_name in ("侵蝕", "膨脹"):
        params["kernel_size"] = st.sidebar.slider("Kernel Size", 1, 21, 3)
        params["iterations"] = st.sidebar.slider("迭代次數", 1, 5, 1)

    elif func_name == "銳化":
        params["intensity"] = st.sidebar.slider("銳化強度", 0.5, 3.0, 1.0, step=0.1)

    elif func_name == "Sobel 邊緣":
        params["direction"] = st.sidebar.selectbox("方向", ["X", "Y", "合併"])
        params["ksize"] = st.sidebar.select_slider("Kernel Size", [1, 3, 5, 7], value=3)

    elif func_name == "輪廓偵測":
        params["all_contours"] = st.sidebar.checkbox("偵測所有輪廓（含內部）", value=False)
        params["min_area"] = st.sidebar.slider("最小輪廓面積（像素）", 0, 1000, 100)

    h, w = image_bgr.shape[:2]
    st.caption(f"影像尺寸：{w} × {h} 像素")

    return {"image_bgr": image_bgr, "func_name": func_name, "params": params}
