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
    m1.metric("B 複製標注", summary.get("b_copied", 0))
    m2.metric("C 整理圖片", summary.get("c_organized", 0))
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
                "b_action": it["b_action"],
                "c_action": it["c_action"],
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

    # Summary metrics
    total = summary.get("total", len(items))
    has_ann_count = sum(1 for it in items if it.get("has_annotation"))
    has_cls_count = sum(1 for it in items if it.get("classification"))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("總圖片數", total)
    m2.metric("有標注", has_ann_count)
    m3.metric("有分類", has_cls_count)
    m4.metric("錯誤", summary.get("errors", 0))

    # 設定摘要
    sf = result.get("source_folder", "")
    copy_ann = result.get("copy_annotations", True)
    org_img = result.get("organize_images", True)

    st.markdown(f"**原始資料夾**：`{sf}`" if sf else "**原始資料夾**：（無法推算）")
    st.markdown(
        f"**B 複製標注 JSON**：{'✅ 啟用' if copy_ann else '⬜ 停用'}　"
        f"**C 整理圖片**：{'✅ 啟用' if org_img else '⬜ 停用'}"
    )

    # 預覽 dataframe
    if items:
        rows = [
            {
                "filename": it["filename"],
                "classification": it["classification"],
                "has_annotation": it["has_annotation"],
                "shape_count": it["shape_count"],
                "b_action": it["b_action"],
                "annotation_dst": it["annotation_dst"],
                "c_action": it["c_action"],
                "organized_dst": it["organized_dst"],
            }
            for it in items
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.warning("沒有圖片資料，請確認已選擇正確的 Manifest。")

    st.divider()

    # 若已有執行結果，顯示之
    execute_result = st.session_state.get("m013_execute_result")
    if execute_result:
        _render_done(execute_result)
        if st.button("🔄 清除結果，重新預覽", key="m013_clear_result"):
            st.session_state.pop("m013_execute_result", None)
            st.rerun()
        return

    # 確認執行按鈕
    if not items:
        return

    b_count = sum(1 for it in items if it.get("b_action") == "copy")
    c_count = sum(1 for it in items if it.get("c_action") == "copy")

    warn_parts = []
    if copy_ann and b_count > 0:
        warn_parts.append(f"將 **{b_count}** 個標注 JSON 寫回影像所在目錄（同名 .json）")
    if org_img and c_count > 0:
        warn_parts.append(f"整理 **{c_count}** 張圖片到分類子目錄")

    if warn_parts:
        st.warning("⚠️ 確認後將執行：\n- " + "\n- ".join(warn_parts) + "\n\n衝突時直接覆蓋。")
    else:
        st.info("ℹ️ 目前條件下沒有需要執行的操作（無標注或無分類）。")

    btn_disabled = len(warn_parts) == 0

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
                "dest_folder": result.get("source_folder", ""),
                "export_dir": result.get("export_dir", ""),
                "copy_annotations": result.get("copy_annotations", True),
                "organize_images": result.get("organize_images", True),
                "dry_run": False,
            }
            result2 = mod.execute_logic(execute_params)
            # Update 完成後把 manifest_id 同步回 module_012.json，
            # 讓 module_012 回到此頁仍選同一個 manifest
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
