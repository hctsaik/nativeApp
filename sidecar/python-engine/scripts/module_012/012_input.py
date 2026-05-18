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
    st.caption(
        "從 Data Feeder（module_010）建立的 DatasetManifest 開啟標注工作階段，"
        "逐張以 X-AnyLabeling 標注，輸出頁即時顯示進度。"
    )

    db_path = _cfg.get_manifest_db_path()
    manifests = _mdb.list_manifests(db_path)

    if not manifests:
        st.warning(
            "尚未建立任何 Manifest，請先執行 **010 - Data Feeder** 選取圖片資料夾。"
        )
        return {"manifest_id": "", "labels": [], "workspace_dir": ""}

    # ── Manifest 選擇（自動預選 shared.json 的 last_manifest_id） ─────────────
    st.subheader("1. 選擇 Manifest")

    shared_id = _cfg.get_shared_manifest_id()

    # 若 shared_id 被外部（例如 module_013 Update）更新，強制重設 selectbox session state。
    # Streamlit 的 key-based selectbox 在 session state 存在時會忽略 index= 參數，
    # 必須在 widget 渲染前主動更新 session state，才能讓 selectbox 跟上外部變化。
    prev_shared = st.session_state.get("_m012_last_shared_id", None)
    if prev_shared != shared_id:
        st.session_state["_m012_last_shared_id"] = shared_id
        new_idx = next(
            (i for i, m in enumerate(manifests) if m["manifest_id"] == shared_id),
            0,
        )
        st.session_state["m012_manifest_idx"] = new_idx

    options_display = [
        f"{m['name']}  ({m.get('item_count', 0)} 張)  — {m['manifest_id'][:8]}…"
        for m in manifests
    ]

    selected_idx = st.selectbox(
        "Manifest",
        options=range(len(options_display)),
        format_func=lambda i: options_display[i],
        key="m012_manifest_idx",
    )

    selected = manifests[selected_idx]
    manifest_id = selected["manifest_id"]

    if shared_id and manifest_id == shared_id:
        st.success(f"✅ 自動銜接自 Data Feeder：**{selected['name']}**")
    else:
        with st.expander("Manifest 摘要", expanded=False):
            c1, c2, c3 = st.columns(3)
            c1.metric("來源", selected.get("source_type", "—"))
            c2.metric("建立時間", (selected.get("created_at") or "—")[:10])
            c3.metric("圖片數", selected.get("item_count", 0))

    st.divider()

    # ── 標注類別 ──────────────────────────────────────────────────────────────
    st.subheader("2. 標注類別")

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
    st.subheader("3. 分類類別")
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

    st.divider()

    # ── Workspace（標注輸出目錄說明） ─────────────────────────────────────────
    workspace_dir = str(_cfg.get_workspace_dir(manifest_id))
    st.subheader("4. 工作區")
    st.info(
        f"標注檔將由 X-AnyLabeling 自動儲存在 Workspace 的 **`annotations/`** 子目錄下（LabelMe JSON 格式），"
        f"不會汙染原始圖片資料夾。\n\n"
        f"Workspace 位於：\n`{workspace_dir}`\n\n"
        f"標注輸出路徑：\n`{workspace_dir}\\annotations\\`"
    )

    return {
        "manifest_id": manifest_id,
        "labels": labels,
        "classification_labels": clf_labels,
        "workspace_dir": workspace_dir,
    }
