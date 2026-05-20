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

    summary = result.get("summary", {})
    items = result.get("items", [])

    total = summary.get("total", len(items))
    ann_count = summary.get("ann_count", sum(1 for it in items if it.get("has_annotation")))
    categories = len({it["classification"] for it in items if it.get("classification")})

    m1, m2, m3 = st.columns(3)
    m1.metric("總圖片數", total)
    m2.metric("有標注", ann_count)
    m3.metric("分類數", categories)

    sf = result.get("source_folder", "")
    org_img = result.get("organize_images", True)
    export_dir = result.get("export_dir", "")

    st.markdown(f"**原始資料夾**：`{sf}`" if sf else "**原始資料夾**：（無法推算）")
    st.markdown(
        f"**整理輸出目錄**：`{export_dir}`　"
        f"**整理圖片**：{'✅ 啟用' if org_img else '⬜ 停用'}"
    )

    if items:
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
    else:
        st.warning("沒有圖片資料，請確認已選擇正確的 Manifest。")

    st.divider()

    execute_result = st.session_state.get("m013_execute_result")
    if execute_result:
        _render_done(execute_result)
        if st.button("🔄 清除結果，重新預覽", key="m013_clear_result"):
            st.session_state.pop("m013_execute_result", None)
            st.rerun()
        return

    if not items:
        return

    c_count = sum(1 for it in items if it.get("c_action") == "copy")

    if org_img and c_count > 0:
        st.warning(f"⚠️ 確認後將複製 **{c_count}** 張圖片（及旁邊的標注 JSON）到分類子目錄。衝突時直接覆蓋。")
    else:
        st.info("ℹ️ 目前條件下沒有需要執行的操作（無分類記錄或整理功能已停用）。")

    btn_disabled = not (org_img and c_count > 0)

    if st.button(
        "✅ 確認執行 Update",
        type="primary",
        key="m013_confirm_execute",
        disabled=btn_disabled,
    ):
        with st.spinner("執行中..."):
            mod = _load_process_mod()
            manifest_id = result.get("manifest_id", "")
            execute_params = {
                "manifest_id": manifest_id,
                "export_dir": result.get("export_dir", ""),
                "organize_images": result.get("organize_images", True),
                "dry_run": False,
            }
            result2 = mod.execute_logic(execute_params)
            if manifest_id and result2.get("mode") == "done":
                try:
                    import importlib.util as _ilu012
                    from pathlib import Path as _Path012
                    _cfg012_spec = _ilu012.spec_from_file_location(
                        "_012_config",
                        _Path012(__file__).resolve().parents[1] / "module_012" / "_config.py"
                    )
                    _cfg012 = _ilu012.module_from_spec(_cfg012_spec)
                    _cfg012_spec.loader.exec_module(_cfg012)
                    _c = _cfg012.load_config()
                    _c["last_manifest_id"] = manifest_id
                    _cfg012.save_config(_c)
                except Exception:
                    pass
            st.session_state["m013_execute_result"] = result2
        st.rerun()


# ── dispatcher ────────────────────────────────────────────────────────────────

def render_output(result: dict) -> None:
    mode = result.get("mode", "error")

    if mode == "error":
        st.error(result.get("error", "未知錯誤"))
        return

    if mode == "preview":
        _render_preview(result)
    elif mode == "done":
        _render_done(result)
    else:
        st.error(f"未知的輸出模式：{mode}")
