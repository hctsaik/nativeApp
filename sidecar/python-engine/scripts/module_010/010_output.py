from __future__ import annotations

import csv
import importlib.util as _ilu
import io
import json
import os
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent

_mdb_spec = _ilu.spec_from_file_location(
    "_manifest_db", _HERE.parent / "shared" / "_manifest_db.py"
)
_mdb = _ilu.module_from_spec(_mdb_spec)
_mdb_spec.loader.exec_module(_mdb)

_cfg_spec = _ilu.spec_from_file_location("_010_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_help_spec = _ilu.spec_from_file_location("_help", _HERE.parent / "shared" / "_help.py")
_help = _ilu.module_from_spec(_help_spec)
_help_spec.loader.exec_module(_help)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CIM_LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", str(_PROJECT_ROOT / "tmp" / "cim_log")))

_SOURCE_LABEL = {"folder": "📁 資料夾", "db": "🗄️ 資料庫", "api": "🌐 API"}


# ─── 統計計算（以 manifest_id 為快取 key）─────────────────────────────────────

def _compute_stats(manifest_id: str, items: list[dict]) -> dict:
    cache_key = f"m010_stats_{manifest_id}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    clf_path = _CIM_LOG_DIR / "config" / f"module_012_classifications_{manifest_id[:12]}.json"
    try:
        classifications: dict = json.loads(clf_path.read_text(encoding="utf-8")) if clf_path.exists() else {}
    except Exception:
        classifications = {}

    annotated = 0
    classified = 0
    for it in items:
        fp = it.get("file_path", "")
        has_json = bool(fp) and Path(fp).with_suffix(".json").exists()
        has_clf = bool(classifications.get(it.get("item_id", "")))
        if has_json:
            annotated += 1
        if has_clf:
            classified += 1

    total = len(items)
    empty = total - len({it["item_id"] for it in items
                          if Path(it.get("file_path", "a")).with_suffix(".json").exists()
                          or classifications.get(it.get("item_id", ""))})

    stats = {
        "total": total,
        "annotated": annotated,
        "classified": classified,
        "empty": empty,
    }
    st.session_state[cache_key] = stats
    return stats


# ─── CSV 匯出 ────────────────────────────────────────────────────────────────

def _build_csv(items: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["#", "item_id", "filename", "width", "height", "file_path"])
    for i, it in enumerate(items, 1):
        fp = it.get("file_path", "")
        w.writerow([i, it.get("item_id", ""), Path(fp).name if fp else "",
                    it.get("width") or "", it.get("height") or "", fp])
    return buf.getvalue().encode("utf-8-sig")


# ─── 主入口 ──────────────────────────────────────────────────────────────────

def render_output(result: dict) -> None:
    _help.render_help_button("module_010", "output")
    mode = result.get("mode", "idle")

    if mode == "idle":
        st.info(
            "**使用方式：**\n\n"
            "1. 在左側 Input 頁面選擇資料來源（資料夾 / 資料庫 / API）\n"
            "2. 填寫路徑設定，點選 ▶ 執行\n"
            "3. 建立完成後，此頁面顯示資料摘要"
        )
        return

    if mode == "error":
        st.error(f"❌ 建立 Manifest 失敗：{result.get('error', '未知錯誤')}")
        return

    manifest_id   = result.get("manifest_id", "")
    manifest_name = result.get("manifest_name", "")
    source_type   = result.get("source_type", "")
    created_at    = result.get("created_at", "")
    source_path   = result.get("source_path", "")

    db_path = _cfg.get_manifest_db_path()
    try:
        all_items = _mdb.get_manifest_items(db_path, manifest_id)
    except Exception:
        all_items = result.get("items", [])

    stats = _compute_stats(manifest_id, all_items)

    # ── 標頭 ──────────────────────────────────────────────────────────────────
    st.success(f"✅ **{manifest_name}**")
    meta_parts: list[str] = [_SOURCE_LABEL.get(source_type, source_type)]
    if created_at:
        meta_parts.append(f"建立：{created_at[:19]}")
    if source_path:
        meta_parts.append(f"`{source_path}`")
    st.caption("　｜　".join(meta_parts))

    st.divider()

    # ── 四個 metrics ──────────────────────────────────────────────────────────
    total      = stats["total"]
    annotated  = stats["annotated"]
    classified = stats["classified"]
    empty      = stats["empty"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("總圖片數", f"{total:,}")
    c2.metric("已標注 BBox", annotated,
              f"{annotated/total*100:.1f}%" if total else "0%")
    c3.metric("已分類", classified,
              f"{classified/total*100:.1f}%" if total else "0%")
    c4.metric("完全空白", empty,
              f"{empty/total*100:.1f}%" if total else "0%")

    if total > 0:
        ann_pct = annotated / total
        st.progress(ann_pct, text=f"標注完成率 {ann_pct*100:.1f}%")

    st.divider()

    # ── CSV 下載 + Manifest ID ────────────────────────────────────────────────
    col_dl, col_id = st.columns([2, 3])
    with col_dl:
        csv_bytes = _build_csv(all_items)
        st.download_button(
            label=f"📤 Export CSV（{total} 筆）",
            data=csv_bytes,
            file_name=f"{manifest_name}.csv",
            mime="text/csv",
        )
    with col_id:
        st.caption(f"Manifest ID：`{manifest_id}`")

    # ── 歷史 Manifest ─────────────────────────────────────────────────────────
    st.divider()
    with st.expander("📋 歷史 Manifest 清單", expanded=False):
        try:
            manifests = list(_mdb.list_manifests(db_path))
            if manifests:
                rows = [
                    {"名稱": m["name"],
                     "圖片數": m.get("item_count", 0),
                     "來源": _SOURCE_LABEL.get(m.get("source_type", ""), ""),
                     "建立時間": (m.get("created_at") or "")[:19],
                     "Manifest ID": m["manifest_id"]}
                    for m in manifests
                ]
                st.dataframe(rows, use_container_width=True, hide_index=True)
            else:
                st.info("尚無歷史記錄。")
        except Exception as exc:
            st.warning(f"無法載入歷史記錄：{exc}")
