from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_013_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_help_spec = _ilu.spec_from_file_location("_help", _HERE.parent / "shared" / "_help.py")
_help = _ilu.module_from_spec(_help_spec)
_help_spec.loader.exec_module(_help)


def _status_icon(status: str) -> str:
    return {"ok": "✅", "failed": "❌", "pending": "⏳"}.get(status, "❓")


def _fmt_upload_status(s: str) -> str:
    if s == "ok":
        return "✅ 上傳成功"
    if s == "skipped":
        return "— 不上傳"
    if s.startswith("failed"):
        return f"❌ {s}"
    return s


def _render_chunk_table(chunk_results: list[dict]) -> None:
    for cr in chunk_results:
        ci = cr["chunk"]
        status = cr["status"]
        count = cr["count"]
        icon = "✅" if status == "ok" else "❌"
        msg = f"{icon} Chunk {ci}: {count} 筆"
        if status == "failed":
            msg += f"　錯誤：{cr.get('error', '')}"
        st.markdown(msg)


def _render_history(manifest_id: str) -> None:
    entries = _cfg.read_sync_history(manifest_id, limit=10)
    if not entries:
        st.caption("尚無同步記錄。")
        return

    rows = []
    for e in reversed(entries):
        started = e.get("started_at", "")[:19].replace("T", " ")
        rows.append({
            "時間": started,
            "系統": e.get("system_name", ""),
            "資料類型": e.get("data_type", ""),
            "送出者": e.get("nt_account", ""),
            "scope": e.get("scope", ""),
            "成功/總計": f"{e.get('ok_count', 0)} / {e.get('scope_count', 0)}",
            "格式": ", ".join(e.get("formats", [])) or "無",
            "狀態": {"ok": "✅ 完全成功", "partial_fail": "⚠️ 部分失敗", "fail": "❌ 全部失敗"}.get(e.get("status", ""), e.get("status", "")),
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_output(result: dict) -> None:
    _help.render_help_button("module_013", "output")
    mode = result.get("mode", "idle")
    manifest_id = result.get("manifest_id", "")

    if mode == "idle":
        st.info("請先在左側 Input 頁籤填寫設定，然後按下 ▶ 執行。")
        if manifest_id:
            with st.expander("同步歷史", expanded=False):
                _render_history(manifest_id)
        return

    if mode == "error":
        st.error(result.get("error", "未知錯誤"))
        return

    if mode == "validation_error":
        st.error(result.get("error", "驗證失敗"))
        issues = result.get("validation_issues", [])
        for vi in issues:
            if vi["severity"] == "error":
                st.error(f"❌ {vi['message']}")
        return

    # ── 成功 / 部分成功 / 失敗 ───────────────────────────────────────────────
    ok = result.get("ok_count", 0)
    failed = result.get("failed_count", 0)
    total = result.get("scope_count", 0)

    if mode == "done":
        st.success(f"✅ 同步完成！{ok} / {total} 筆成功送出。")
    elif mode == "partial_fail":
        st.warning(f"⚠️ 部分成功：{ok} 筆 ok，{failed} 筆失敗。")
    else:  # fail
        st.error(f"❌ 全部失敗：{failed} 筆。")

    # 指標列
    c1, c2, c3 = st.columns(3)
    c1.metric("成功送出", ok)
    c2.metric("失敗", failed)
    c3.metric("格式包上傳", _fmt_upload_status(result.get("export_upload_status", "")))

    st.divider()

    # chunk 詳情
    chunk_results = result.get("chunk_results", [])
    if chunk_results:
        with st.expander(f"Chunk 送出詳情（共 {len(chunk_results)} 個）", expanded=failed > 0):
            _render_chunk_table(chunk_results)

    # 格式包上傳
    upload_status = result.get("export_upload_status", "")
    if upload_status not in ("skipped", "ok", ""):
        st.warning(f"格式包上傳：{upload_status}")

    # 歷史
    st.divider()
    with st.expander("同步歷史（最近 10 筆）", expanded=False):
        _render_history(manifest_id)
