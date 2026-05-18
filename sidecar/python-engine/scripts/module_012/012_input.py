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

_DEFAULT_LABELS = ["物件A", "物件B", "物件C"]


# ─── 主入口 ──────────────────────────────────────────────────────────────────

def render_input() -> dict:
    st.subheader("🏷️ Annotation Session — 標注作業設定")

    db_path = _cfg.get_manifest_db_path()
    manifests = _mdb.list_manifests(db_path)

    if not manifests:
        st.warning(
            "尚未建立任何 Manifest，請先執行 **010 - Data Feeder** 選取圖片資料夾。"
        )
        return {"manifest_id": "", "labels": [], "classification_labels": [], "workspace_dir": ""}

    # ── 自動銜接最後一個 manifest（優先用 shared.json 的 last_manifest_id） ───
    shared_id = _cfg.get_shared_manifest_id()
    selected = next(
        (m for m in manifests if m["manifest_id"] == shared_id),
        manifests[0],
    )
    manifest_id = selected["manifest_id"]

    st.info(
        f"📦 **{selected['name']}**　{selected.get('item_count', 0)} 張　"
        f"　｜　若要切換請回 Data Feeder 重新執行"
    )

    st.divider()

    # ── 標注類別 ──────────────────────────────────────────────────────────────
    st.subheader("1. 標注類別")

    cfg = _cfg.load_config()
    if "m012_labels_raw" not in st.session_state:
        saved = cfg.get("annotation_labels", _DEFAULT_LABELS)
        st.session_state["m012_labels_raw"] = "\n".join(saved)

    labels_raw = st.text_area(
        "每行一個類別名稱",
        key="m012_labels_raw",
        height=120,
        help="X-AnyLabeling 啟動時會自動載入這些類別，僅允許標注此清單內的標籤。",
    )
    labels = [l.strip() for l in labels_raw.splitlines() if l.strip()]
    if labels:
        st.caption(f"共 **{len(labels)}** 個類別：{', '.join(labels[:8])}" +
                   ("…" if len(labels) > 8 else ""))
    else:
        st.warning("請至少輸入一個標注類別。")

    st.divider()

    # ── 分類類別 ──────────────────────────────────────────────────────────────
    st.subheader("2. 分類類別")
    st.caption("可選：在 Output 頁面對每張圖片快速分類（與 X-AnyLabeling 標注框無關）")

    if "m012_clf_raw" not in st.session_state:
        saved_clf = cfg.get("classification_labels", [])
        st.session_state["m012_clf_raw"] = "\n".join(saved_clf) if saved_clf else ""

    clf_raw = st.text_area(
        "每行一個類別（留空表示不使用分類功能）",
        key="m012_clf_raw",
        height=80,
    )
    clf_labels = [l.strip() for l in clf_raw.splitlines() if l.strip()]

    workspace_dir = str(_cfg.get_workspace_dir(manifest_id))

    return {
        "manifest_id": manifest_id,
        "labels": labels,
        "classification_labels": clf_labels,
        "workspace_dir": workspace_dir,
    }
