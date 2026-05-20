from __future__ import annotations

import importlib.util as _ilu
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

_DEFAULT_LABELS: list[str] = []
_ANNOTATION_TOOLS = {
    "X-AnyLabeling": "x-anylabeling",
    "LabelMe": "labelme",
}


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
    st.subheader("🏷️ 開始標注前確認")

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
