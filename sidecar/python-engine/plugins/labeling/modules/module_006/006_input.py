from __future__ import annotations

import importlib.util as _ilu
import json
import os
from pathlib import Path

import streamlit as st

try:
    from _config import get_annotation_labels, set_annotation_labels
except ImportError:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _config import get_annotation_labels, set_annotation_labels

_PROJECT_ROOT = Path(__file__).resolve().parents[6]
_DEFAULT_ANIMAL_DIR = _PROJECT_ROOT / "testData" / "animal"
_DEFAULT_DB = _DEFAULT_ANIMAL_DIR / "animals.db"
_DEFAULT_WORKSPACE = _PROJECT_ROOT / "tmp" / "animal-annotation"

# ── Manifest DB 動態載入 ───────────────────────────────────────────────────────

try:
    _HERE_006 = Path(__file__).resolve().parent
    _spec_mdb = _ilu.spec_from_file_location(
        "_manifest_db",
        _HERE_006.parent / "shared" / "_manifest_db.py",
    )
    _mdb_006 = _ilu.module_from_spec(_spec_mdb)
    _spec_mdb.loader.exec_module(_mdb_006)
    _MANIFEST_DB_AVAILABLE = True
except Exception:
    _MANIFEST_DB_AVAILABLE = False


def _get_manifest_db_path_006() -> Path:
    _cim_log = Path(os.environ.get(
        "CIM_LOG_DIR",
        str(Path(__file__).resolve().parents[6] / "tmp" / "cim_log"),
    ))
    return _cim_log / "db" / "manifest.sqlite"

CATEGORIES = ["ALL", "貓", "狗", "大象"]
ANNOTATION_TOOLS = {
    "X-AnyLabeling": "x-anylabeling",
    "LabelMe": "labelme",
    "ISAT": "isat",
}


# ── step state helpers ────────────────────────────────────────────────────────

def _session_exists(workspace_root: str) -> bool:
    return (Path(workspace_root) / "session.json").exists()


def _load_session(workspace_root: str) -> dict | None:
    p = Path(workspace_root) / "session.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


# ── stepper UI (2 steps) ──────────────────────────────────────────────────────

def _render_stepper(current_step: int) -> int:
    """Render 2-step indicators; return the step the user clicked."""
    STEPS = [
        (1, "瀏覽標記"),
        (2, "準備標注專案"),
    ]

    cols = st.columns([3, 1, 3])
    chosen = current_step

    for idx, (step_num, label) in enumerate(STEPS):
        col = cols[idx * 2]
        is_active = step_num == current_step
        is_done   = step_num < current_step

        with col:
            if is_active:
                st.markdown(
                    f"<div style='text-align:center;padding:8px 0;"
                    f"border-bottom:3px solid #1f77b4;color:#1f77b4;font-weight:700'>"
                    f"{'✅' if is_done else '●'} {step_num}. {label}</div>",
                    unsafe_allow_html=True,
                )
            else:
                if st.button(
                    f"{'✅' if is_done else '○'} {step_num}. {label}",
                    key=f"step_btn_{step_num}",
                    use_container_width=True,
                ):
                    chosen = step_num

        if idx < len(STEPS) - 1:
            with cols[idx * 2 + 1]:
                st.markdown(
                    "<div style='text-align:center;padding:10px 0;color:#888'>──►</div>",
                    unsafe_allow_html=True,
                )

    return chosen


# ── per-step forms ────────────────────────────────────────────────────────────

def _render_browse(workspace_root: str) -> dict:
    col_cat, col_ws = st.columns([1, 2])
    with col_cat:
        category = st.selectbox("篩選類別", CATEGORIES, index=0)
    with col_ws:
        with st.expander("路徑設定 ＆ 標注類別", expanded=False):
            db_path   = st.text_input("資料庫路徑",  value=str(_DEFAULT_DB))
            image_dir = st.text_input("影像目錄",    value=str(_DEFAULT_ANIMAL_DIR))
            workspace_root = st.text_input(
                "Annotation Workspace",
                value=workspace_root,
            )
            st.divider()
            st.caption("**標注類別**（傳入 X-AnyLabeling 的 classes，與上方動物篩選無關）")
            labels_raw = st.text_area(
                "標注類別（每行一個）",
                value="\n".join(get_annotation_labels()),
                height=100,
                key="ann_labels_area",
                label_visibility="collapsed",
            )
            parsed = [lbl.strip() for lbl in labels_raw.splitlines() if lbl.strip()]
            if parsed:
                set_annotation_labels(parsed)

    if not Path(db_path).exists():
        st.error(f"找不到資料庫：{db_path}")

    return {
        "mode": "browse",
        "filter": category,
        "db_path": db_path,
        "image_dir": image_dir,
        "workspace_root": workspace_root,
    }


def _render_phase1(workspace_root: str) -> dict:
    st.markdown("##### 設定標注專案")
    col1, col2 = st.columns(2)
    with col1:
        category   = st.selectbox("篩選動物類別", CATEGORIES, index=0,
                                  help="要匯入 X-AnyLabeling 的動物類別")
        tool_label = st.selectbox("Labeling Tool", list(ANNOTATION_TOOLS), index=0)
        default_labels = ", ".join(get_annotation_labels())
        labels_raw = st.text_input(
            "標注 Labels（逗號分隔）",
            value=default_labels,
            help="X-AnyLabeling 的標注類別，例如：眼睛, 鼻子, 嘴巴。與上方動物篩選無關。",
        )
    with col2:
        db_path    = st.text_input("資料庫路徑", value=str(_DEFAULT_DB),  key="p1_db")
        image_dir  = st.text_input("影像目錄",   value=str(_DEFAULT_ANIMAL_DIR), key="p1_img")

    workspace_root = st.text_input("Workspace 根目錄", value=workspace_root)
    launch_tool    = st.checkbox("準備完成後自動啟動 labeling tool", value=True)

    labels = [lbl.strip() for lbl in labels_raw.split(",") if lbl.strip()]
    if labels:
        set_annotation_labels(labels)
    return {
        "mode": "xany_phase1",
        "annotation_tool": ANNOTATION_TOOLS[tool_label],
        "category":       category,
        "labels":         labels,
        "db_path":        db_path,
        "image_dir":      image_dir,
        "workspace_root": workspace_root,
        "launch_labeling_tool": launch_tool,
        "launch_xany":    launch_tool,
    }


# ── main entry ────────────────────────────────────────────────────────────────

def render_input() -> dict:
    st.subheader(":material/label: 動物影像標注專案")
    st.caption(
        "**工作流程：** "
        "①  步驟 1 瀏覽圖片 / 驗收標注 / 匯出訓練資料　"
        "→  ②  步驟 2 建立 X-AnyLabeling 標注專案並開啟標注工具"
    )

    with st.expander("📖 使用說明", expanded=False):
        _guide_path = Path(__file__).resolve().parent / "guide.html"
        if _guide_path.exists():
            import streamlit.components.v1 as _components
            _components.html(_guide_path.read_text(encoding="utf-8"), height=700, scrolling=True)

    # ── Manifest 選擇（來自 Data Feeder，選填）────────────────────────────────
    with st.expander("📦 使用 Data Feeder Manifest（選填）", expanded=False):
        if _MANIFEST_DB_AVAILABLE:
            try:
                _mdb_path = _get_manifest_db_path_006()
                if _mdb_path.exists():
                    _manifests = _mdb_006.list_manifests(_mdb_path)
                    if _manifests:
                        _opts = ["（不使用，使用原始設定）"] + [
                            f"{m['name']}（{m['item_count']} 筆）" for m in _manifests
                        ]
                        _sel = st.selectbox("選擇 Manifest", _opts, key="m006_manifest_sel")
                        if _sel != _opts[0]:
                            _idx = _opts.index(_sel) - 1
                            st.session_state["m006_manifest_id"] = _manifests[_idx]["manifest_id"]
                            st.info(
                                f"✅ 將使用 Manifest：{_manifests[_idx]['name']}"
                                f"（{_manifests[_idx]['item_count']} 筆圖片）"
                            )
                        else:
                            st.session_state["m006_manifest_id"] = None
                    else:
                        st.info("尚無 Manifest。請先在 Module 010 Data Feeder 建立資料來源。")
                        st.session_state["m006_manifest_id"] = None
                else:
                    st.caption("Manifest 資料庫尚未建立，請先使用 Module 010 Data Feeder。")
                    st.session_state["m006_manifest_id"] = None
            except Exception as _e:
                st.caption(f"Manifest 載入失敗（{_e}），使用原始設定。")
                st.session_state["m006_manifest_id"] = None
        else:
            st.caption("shared/_manifest_db.py 尚未安裝，無法使用 Manifest 功能。")

    if "annotation_step" not in st.session_state:
        st.session_state.annotation_step = 1

    workspace_root = str(_DEFAULT_WORKSPACE)

    chosen = _render_stepper(st.session_state.annotation_step)
    if chosen != st.session_state.annotation_step:
        st.session_state.annotation_step = chosen
        st.rerun()

    st.divider()

    step = st.session_state.annotation_step
    if step == 1:
        result = _render_browse(workspace_root)
    else:
        result = _render_phase1(workspace_root)

    result["manifest_id"] = st.session_state.get("m006_manifest_id")
    return result
