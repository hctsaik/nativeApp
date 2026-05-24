from __future__ import annotations

import importlib.util as _ilu
import subprocess
import sys
from pathlib import Path

import streamlit as st

# ─── 動態載入 _config + _manifest_db ─────────────────────────────────────────

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_012_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_mdb_spec = _ilu.spec_from_file_location(
    "_manifest_db", _HERE.parent / "shared" / "_manifest_db.py"
)
_mdb = _ilu.module_from_spec(_mdb_spec)
_mdb_spec.loader.exec_module(_mdb)

_ai_cfg_spec = _ilu.spec_from_file_location(
    "_016_config", _HERE.parent / "module_016" / "_config.py"
)
_ai_cfg = _ilu.module_from_spec(_ai_cfg_spec)
_ai_cfg_spec.loader.exec_module(_ai_cfg)

_help_spec = _ilu.spec_from_file_location("_help", _HERE.parent / "shared" / "_help.py")
_help = _ilu.module_from_spec(_help_spec)
_help_spec.loader.exec_module(_help)

_DEFAULT_LABELS: list[str] = []
_ANNOTATION_TOOLS = {
    "X-AnyLabeling": "x-anylabeling",
    "LabelMe": "labelme",
}


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


def _parse_lines(raw: str) -> list[str]:
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _duplicate_labels(labels: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for label in labels:
        key = label.casefold()
        if key in seen and label not in duplicates:
            duplicates.append(label)
        seen.add(key)
    return duplicates


# ─── 主入口 ──────────────────────────────────────────────────────────────────

def render_input() -> dict:
    _help.render_help_button("module_012", "input", "🏷️ 開始標注前確認")

    db_path = _cfg.get_manifest_db_path()
    manifests = _mdb.list_manifests(db_path)

    if not manifests:
        st.warning(
            "尚未建立任何 Manifest，請先執行 **010 - Data Feeder** 選取圖片資料夾。"
        )
        return {
            "manifest_id": "",
            "annotation_tool": "x-anylabeling",
            "labels": [],
            "classification_labels": [],
            "autorefresh_enabled": True,
            "autorefresh_seconds": 10,
        }

    # ── 自動銜接最後一個 manifest（優先用 shared.json 的 last_manifest_id） ───
    cfg = _cfg.load_config()
    shared_id = _cfg.get_shared_manifest_id()
    selected = next(
        (m for m in manifests if m["manifest_id"] == shared_id),
        manifests[0],
    )
    manifest_id = selected["manifest_id"]

    st.info(
        f"目前資料集：**{selected['name']}**｜{selected.get('item_count', 0)} 張圖片"
        "｜不是這批？請回 Data Feeder 重新選取。"
    )

    # ── 標注類別 ──────────────────────────────────────────────────────────────
    st.markdown("#### 標注類別")

    if "m012_labels_raw" not in st.session_state:
        saved = cfg.get("annotation_labels", _DEFAULT_LABELS)
        st.session_state["m012_labels_raw"] = "\n".join(saved)

    labels_raw = st.text_area(
        "每行一個類別名稱",
        key="m012_labels_raw",
        height=120,
        placeholder="例：scratch\ndent\nstain",
        help="啟動標注工具時會載入這些類別，空白行會自動忽略。",
    )
    labels = _parse_lines(labels_raw)
    duplicate_labels = _duplicate_labels(labels)
    if labels:
        st.success(
            f"將建立 {len(labels)} 個標注類別：{', '.join(labels[:8])}"
            + ("…" if len(labels) > 8 else "")
        )
        if duplicate_labels:
            st.warning(f"有重複類別：{', '.join(duplicate_labels[:5])}")
    else:
        st.warning("請先輸入標注工具中會使用的框選類別。")

    # ── 分類類別 ──────────────────────────────────────────────────────────────
    if "m012_clf_raw" not in st.session_state:
        saved_clf = cfg.get("classification_labels", [])
        st.session_state["m012_clf_raw"] = "\n".join(saved_clf) if saved_clf else ""

    # ── 自動刷新 ──────────────────────────────────────────────────────────────
    if "m012_autorefresh_enabled" not in st.session_state:
        st.session_state["m012_autorefresh_enabled"] = bool(
            cfg.get("autorefresh_enabled", True)
        )
    if "m012_autorefresh_seconds" not in st.session_state:
        st.session_state["m012_autorefresh_seconds"] = int(
            cfg.get("autorefresh_seconds", 10)
        )

    with st.expander("圖片快速分類，可選", expanded=bool(st.session_state["m012_clf_raw"])):
        st.caption("用於標注列表頁替整張圖片分類，不會寫入標注框 JSON。")
        clf_raw = st.text_area(
            "每行一個圖片分類選項",
            key="m012_clf_raw",
            height=80,
            placeholder="例：OK\nNG\n需複檢",
        )
        clf_labels = _parse_lines(clf_raw)
        if clf_labels:
            st.caption(f"將顯示 {len(clf_labels)} 個快速分類選項。")
        else:
            st.caption("未啟用圖片快速分類。")

    saved_tool = cfg.get("annotation_tool", "x-anylabeling")
    tool_labels = list(_ANNOTATION_TOOLS.keys())
    default_tool_index = 0
    for idx, label in enumerate(tool_labels):
        if _ANNOTATION_TOOLS[label] == saved_tool:
            default_tool_index = idx
            break

    with st.expander("進階設定", expanded=False):
        selected_tool_label = st.selectbox(
            "標注工具",
            tool_labels,
            index=default_tool_index,
            help="標注列表頁的工具按鈕會依此設定開啟對應工具。",
        )
        annotation_tool = _ANNOTATION_TOOLS[selected_tool_label]

        st.caption(
            "自動重新掃描標注結果："
            f"{'開啟' if st.session_state['m012_autorefresh_enabled'] else '關閉'}，"
            f"每 {st.session_state['m012_autorefresh_seconds']} 秒"
        )
        refresh_cols = st.columns([1, 1])
        with refresh_cols[0]:
            autorefresh_enabled = st.checkbox(
                "啟用自動重新掃描",
                key="m012_autorefresh_enabled",
                help="開啟後標注列表頁會定期更新，讀取圖片旁邊的標注 JSON。",
            )
        with refresh_cols[1]:
            autorefresh_seconds = int(
                st.number_input(
                    "掃描間隔（秒）",
                    min_value=5,
                    max_value=300,
                    step=5,
                    key="m012_autorefresh_seconds",
                    disabled=not autorefresh_enabled,
                )
            )

    # ── AI 模型設定 ───────────────────────────────────────────────────────────
    ai_cfg = _ai_cfg.load_config()

    if "_m012_ai_model_chosen" in st.session_state:
        st.session_state["m012_ai_model_path"] = st.session_state.pop("_m012_ai_model_chosen")
    if "m012_ai_model_path" not in st.session_state:
        st.session_state["m012_ai_model_path"] = ai_cfg.get("model_path", "")
    if "m012_ai_model_type" not in st.session_state:
        st.session_state["m012_ai_model_type"] = ai_cfg.get("model_type", "yolo")
    if "m012_ai_conf" not in st.session_state:
        st.session_state["m012_ai_conf"] = float(ai_cfg.get("conf_threshold", 0.25))
    if "m012_ai_overwrite" not in st.session_state:
        st.session_state["m012_ai_overwrite"] = bool(ai_cfg.get("overwrite_existing", False))

    with st.expander("🤖 AI 模型設定", expanded=bool(st.session_state["m012_ai_model_path"])):
        st.caption("設定 AI Pre-label 使用的模型，Output 頁的 AI 按鈕會依此執行推論。")

        model_type_options = ["YOLO（Object Detection）", "Image Classifier（分類）"]
        model_type_index = 0 if st.session_state["m012_ai_model_type"] == "yolo" else 1
        selected_model_type = st.radio(
            "推論模式",
            model_type_options,
            index=model_type_index,
            horizontal=True,
            key="m012_ai_model_type_radio",
        )
        model_type_key = "yolo" if "YOLO" in selected_model_type else "classifier"

        col_path, col_btn = st.columns([5, 1])
        with col_path:
            ai_model_path = st.text_input(
                "模型路徑（.pt）",
                key="m012_ai_model_path",
                placeholder="C:/models/best.pt",
            )
        with col_btn:
            st.write("")
            if st.button("📂", key="m012_ai_browse", help="瀏覽模型檔案"):
                chosen = _browse_file("選擇模型檔案", "[('PyTorch model','*.pt'),('All','*.*')]")
                if chosen:
                    st.session_state["_m012_ai_model_chosen"] = chosen
                    st.rerun()

        if ai_model_path and not Path(ai_model_path).exists():
            st.warning("找不到模型檔案，請確認路徑正確。")
        elif ai_model_path:
            st.caption(f"✅ 模型已選取。首次使用 AI 按鈕時會載入模型（約 10–30 秒），之後即時生效。")

        ai_conf = st.slider(
            "Confidence Threshold",
            min_value=0.01, max_value=1.0,
            value=st.session_state["m012_ai_conf"],
            step=0.01, format="%.2f",
            key="m012_ai_conf",
        )
        ai_overwrite = st.checkbox(
            "覆蓋已有標注",
            value=st.session_state["m012_ai_overwrite"],
            key="m012_ai_overwrite",
            help="勾選後，即使圖片已有 .json 標注也會重新推論並覆蓋。",
        )

        new_ai_cfg = {
            **ai_cfg,
            "model_type": model_type_key,
            "model_path": ai_model_path,
            "conf_threshold": ai_conf,
            "overwrite_existing": ai_overwrite,
        }
        if new_ai_cfg != ai_cfg:
            try:
                _ai_cfg.save_config(new_ai_cfg)
            except Exception:
                pass

    # 儲存分類類別到 config，避免 session 重啟後消失
    try:
        cfg["classification_labels"] = clf_labels
        _cfg.save_config(cfg)
    except Exception:
        pass

    return {
        "manifest_id": manifest_id,
        "annotation_tool": annotation_tool,
        "labels": labels,
        "classification_labels": clf_labels,
        "autorefresh_enabled": autorefresh_enabled,
        "autorefresh_seconds": autorefresh_seconds,
    }
