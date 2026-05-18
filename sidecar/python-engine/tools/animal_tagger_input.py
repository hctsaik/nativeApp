from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from tool_comms import notify_complete, notify_start
from tool_result import write_result

TOOL_ID = os.environ.get("CIM_TOOL_ID", "animal-tagger")
LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", "/tmp"))
RESULT_FILE = LOG_DIR / f"{TOOL_ID}_result.json"

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_ANIMAL_DIR = _PROJECT_ROOT / "testData" / "animal"
_DEFAULT_DB = _DEFAULT_ANIMAL_DIR / "animals.db"

CATEGORIES = ["ALL", "貓", "狗", "大象"]


def main() -> None:
    st.set_page_config(page_title="動物影像標記 — Input", layout="wide")
    st.title("動物影像標記系統")

    st.subheader("篩選條件")
    category = st.selectbox("選擇類別", CATEGORIES, index=0)

    st.divider()
    with st.expander("進階：路徑設定", expanded=False):
        db_path = st.text_input("資料庫路徑", value=str(_DEFAULT_DB))
        image_dir = st.text_input("影像目錄", value=str(_DEFAULT_ANIMAL_DIR))

    st.markdown(f"**資料庫**：`{db_path}`")
    st.markdown(f"**影像目錄**：`{image_dir}`")

    if not Path(db_path).exists():
        st.error(f"找不到資料庫：{db_path}")
        return

    if st.button("▶ 載入資料", type="primary"):
        notify_start()
        user_input = {
            "filter": category,
            "db_path": str(Path(db_path)),
            "image_dir": str(Path(image_dir)),
        }
        write_result(RESULT_FILE, user_input, {})
        notify_complete()
        st.success(f"已載入「{category}」類別，請切換至 Output 頁籤查看並標記。")


if __name__ == "__main__":
    main()
