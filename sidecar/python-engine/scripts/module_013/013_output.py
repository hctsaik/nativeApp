from __future__ import annotations

import importlib.util
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent
_PROCESS_FILE = _HERE / "013_process.py"


def _load_process_mod():
    spec = importlib.util.spec_from_file_location("_013_process", _PROCESS_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _render_done(result: dict) -> None:
    """顯示 dry_run=False 的執行結果。"""
    summary = result.get("summary", {})
    st.success("✅ Update 完成！")

    m1, m2, m3 = st.columns(3)
    m1.metric("整理圖片", summary.get("c_organized", 0))
    m2.metric("帶走標注 JSON", summary.get("ann_exported", 0))
    m3.metric("錯誤數", summary.get("errors", 0))

    out_path = result.get("output_json_path", "")
    if out_path and not out_path.startswith("["):
        st.info(f"輸出 JSON：`{out_path}`")
    elif out_path:
        st.warning(f"輸出 JSON：{out_path}")

    items = result.get("items", [])
    if items:
        st.subheader("執行結果")
        rows = [
            {
                "filename": it["filename"],
                "classification": it["classification"],
                "has_annotation": it["has_annotation"],
                "c_action": it["c_action"],
                "organized_dst": it["organized_dst"],
                "ann_export_dst": it["ann_export_dst"],
                "status": it["status"],
                "error_msg": it["error_msg"],
            }
            for it in items
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_preview(result: dict) -> None:
    """顯示 dry_run=True 的預覽，並提供確認執行按鈕。"""
    st.subheader("📋 Update 預覽")

    items = result.get("items", [])
    org_img = result.get("organize_images", True)
    export_dir = result.get("export_dir", "")
    sf = result.get("source_folder", "")

    c_count = sum(1 for it in items if it.get("c_action") == "copy")
    categories = len({it["classification"] for it in items if it.get("classification")})
    ann_in_copy = sum(1 for it in items if it.get("c_action") == "copy" and it.get("has_annotation"))

    m1, m2, m3 = st.columns(3)
    m1.metric("待複製圖片", c_count)
    m2.metric("分類數", categories)
    m3.metric("含標注", ann_in_copy)

    st.markdown(f"**原始資料夾**：`{sf}`" if sf else "**原始資料夾**：（無法推算）")
    st.markdown(
        f"**輸出目錄**：`{export_dir}`　"
        f"**整理圖片**：{'✅ 啟用' if org_img else '⬜ 停用'}"
    )

    st.divider()

    execute_result = st.session_state.get("m013_execute_result")
    if execute_result:
        _render_done(execute_result)
        if st.button("🔄 清除結果，重新預覽", key="m013_clear_result"):
            st.session_state.pop("m013_execute_result", None)
            st.rerun()
        return

    if not items:
        st.warning("沒有圖片資料，請確認已選擇正確的 Manifest。")
        return

    # ── 確認摘要 + 執行按鈕（在詳細列表之前）────────────────────────────────────
    if org_img and c_count > 0:
        ann_note = f"（含 {ann_in_copy} 個標注 JSON）" if ann_in_copy else ""
        st.warning(
            f"確認後將複製 **{c_count}** 張圖片{ann_note}到 `{export_dir}`。衝突檔案直接覆蓋。"
        )
    else:
        st.info("目前沒有已分類的圖片需要複製。請先在 Annotation Session 完成分類。")

    if st.button(
        "✅ 確認執行 Update",
        type="primary",
        key="m013_confirm_execute",
        disabled=not (org_img and c_count > 0),
    ):
        with st.spinner("執行中..."):
            mod = _load_process_mod()
            manifest_id = result.get("manifest_id", "")
            execute_params = {
                "manifest_id": manifest_id,
                "export_dir": export_dir,
                "organize_images": org_img,
                "dry_run": False,
            }
            result2 = mod.execute_logic(execute_params)
            if manifest_id and result2.get("mode") == "done":
                try:
                    import importlib.util as _ilu012
                    import json as _json012
                    from pathlib import Path as _Path012
                    _cfg012_spec = _ilu012.spec_from_file_location(
                        "_012_config",
                        _Path012(__file__).resolve().parents[1] / "module_012" / "_config.py"
                    )
                    _cfg012 = _ilu012.module_from_spec(_cfg012_spec)
                    _cfg012_spec.loader.exec_module(_cfg012)
                    _cfg012_path = _cfg012._config_path()
                    try:
                        _raw = _json012.loads(_cfg012_path.read_text(encoding="utf-8")) if _cfg012_path.exists() else {}
                    except Exception:
                        _raw = {}
                    _raw["last_manifest_id"] = manifest_id
                    _cfg012_path.parent.mkdir(parents=True, exist_ok=True)
                    _cfg012_path.write_text(_json012.dumps(_raw, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
            st.session_state["m013_execute_result"] = result2
        st.rerun()

    # ── 詳細清單（預設收合，避免遮擋確認按鈕）───────────────────────────────────
    st.divider()
    with st.expander(f"查看詳細清單（{len(items)} 張）", expanded=False):
        rows = [
            {
                "filename": it["filename"],
                "classification": it["classification"],
                "has_annotation": it["has_annotation"],
                "shape_count": it["shape_count"],
                "c_action": it["c_action"],
                "organized_dst": it["organized_dst"],
                "ann_export_dst": it["ann_export_dst"],
            }
            for it in items
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)


# ── dispatcher ────────────────────────────────────────────────────────────────

def render_output(result: dict) -> None:
    mode = result.get("mode", "idle")

    if mode == "idle":
        st.info("請先在 Input 頁籤確認設定，然後按下 ▶ 執行，預覽結果會顯示在這裡。")
        return

    if mode == "error":
        st.error(result.get("error", "未知錯誤"))
        return

    if mode == "preview":
        _render_preview(result)
    elif mode == "done":
        _render_done(result)
    else:
        st.error(f"未知的輸出模式：{mode}")
