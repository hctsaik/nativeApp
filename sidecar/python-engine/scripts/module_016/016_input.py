from __future__ import annotations

import importlib.util as _ilu
import subprocess
import sys
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_016_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_mdb_spec = _ilu.spec_from_file_location(
    "_manifest_db", _HERE.parent / "shared" / "_manifest_db.py"
)
_mdb = _ilu.module_from_spec(_mdb_spec)
_mdb_spec.loader.exec_module(_mdb)

_help_spec = _ilu.spec_from_file_location("_help", _HERE.parent / "shared" / "_help.py")
_help = _ilu.module_from_spec(_help_spec)
_help_spec.loader.exec_module(_help)


def _browse_file(title: str, filetypes: str) -> str:
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             f"import tkinter as tk; from tkinter import filedialog; "
             f"root=tk.Tk(); root.withdraw(); root.wm_attributes('-topmost',True); "
             f"p=filedialog.askopenfilename(title='{title}',filetypes={filetypes}); "
             f"root.destroy(); print(p or '',end='')"],
            capture_output=True, text=True, timeout=60,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def render_input() -> dict:
    st.subheader("🤖 AI Pre-labeling — 模型自動預標注")
    st.caption("選擇模型，對當前 Manifest 的圖片批次推論，結果寫成 X-AnyLabeling JSON 供人工修正。")
    _help.render_help_button("module_016", "input")

    db_path = _cfg.get_manifest_db_path()
    manifests = _mdb.list_manifests(db_path)

    if not manifests:
        st.warning("尚未建立任何 Manifest，請先執行 **010 - Data Feeder**。")
        return {"manifest_id": ""}

    # 自動用 Data Feeder 最後選取的 manifest
    shared_id = _cfg.get_shared_manifest_id()
    manifests_list = list(manifests)
    selected = next(
        (m for m in manifests_list if m["manifest_id"] == shared_id),
        manifests_list[0],
    )
    manifest_id = selected["manifest_id"]
    total_items: int = selected.get("item_count", 0)
    st.info(f"📦 **{selected['name']}**　{total_items} 張　｜　若要切換請回 Data Feeder")

    st.divider()
    cfg = _cfg.load_config()

    # ── 模型類型 ──────────────────────────────────────────────────────────────
    st.subheader("1. 模型類型")
    model_type = st.radio(
        "推論模式",
        ["YOLO（Object Detection）", "Image Classifier（分類）"],
        index=0 if cfg.get("model_type", "yolo") == "yolo" else 1,
        horizontal=True,
        key="m016_model_type",
    )
    model_type_key = "yolo" if "YOLO" in model_type else "classifier"

    with st.expander("模式說明", expanded=False):
        st.markdown("""
- **YOLO**：輸出 bbox + label，寫成 X-AnyLabeling rectangle shapes。支援 YOLOv5/v8/v11 `.pt` 權重。
- **Classifier**：輸出整張圖片的分類 label，寫成 X-AnyLabeling 的 `flags` 欄位，
  同時更新 module_012 的分類結果（ImageFolder Export 可直接使用）。
""")

    st.divider()

    # ── 模型檔案 ──────────────────────────────────────────────────────────────
    st.subheader("2. 模型檔案")

    if "_m016_model_chosen" in st.session_state:
        st.session_state["m016_model_path"] = st.session_state.pop("_m016_model_chosen")
    if "m016_model_path" not in st.session_state:
        st.session_state["m016_model_path"] = cfg.get("model_path", "")

    col_path, col_btn = st.columns([5, 1])
    with col_path:
        model_path = st.text_input(
            "模型路徑（.pt）",
            key="m016_model_path",
            placeholder="C:/models/best.pt",
        )
    with col_btn:
        st.write("")
        if st.button("📂 瀏覽", key="m016_browse_model"):
            chosen = _browse_file("選擇模型檔案", "[('PyTorch model','*.pt'),('All','*.*')]")
            if chosen:
                st.session_state["_m016_model_chosen"] = chosen
                st.rerun()

    if model_path and not Path(model_path).exists():
        st.warning("找不到模型檔案，請確認路徑正確。")

    st.divider()

    # ── 推論參數 ──────────────────────────────────────────────────────────────
    st.subheader("3. 推論參數")

    conf = st.slider(
        "信心分數門檻（Confidence Threshold）",
        min_value=0.01, max_value=1.0,
        value=float(cfg.get("conf_threshold", 0.25)),
        step=0.01, format="%.2f",
        key="m016_conf",
        help="低於此分數的預測結果會被丟棄。",
    )

    overwrite = st.checkbox(
        "覆蓋已有標注（已存在 .json 的圖片也重新推論）",
        value=cfg.get("overwrite_existing", False),
        key="m016_overwrite",
        help="預設跳過已有 .json 標注的圖片，只對新圖片推論。",
    )

    if total_items > 0:
        st.info(f"將對全部 **{total_items}** 張圖片推論。推論進度可在右側 Output 查看。")

    # 儲存設定
    try:
        cfg["model_type"] = model_type_key
        cfg["model_path"] = model_path
        cfg["conf_threshold"] = conf
        cfg["overwrite_existing"] = overwrite
        _cfg.save_config(cfg)
    except Exception:
        pass

    return {
        "manifest_id": manifest_id,
        "model_type": model_type_key,
        "model_path": model_path,
        "conf_threshold": conf,
        "overwrite_existing": overwrite,
    }
