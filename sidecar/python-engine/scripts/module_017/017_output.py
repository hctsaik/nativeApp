from __future__ import annotations

import importlib.util
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent
_PROCESS_FILE = _HERE / "017_process.py"


def _load_process_mod():
    spec = importlib.util.spec_from_file_location("_017_process", _PROCESS_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _refresh(result: dict) -> dict:
    """Re-scan labels from disk and update session_state cache."""
    mod = _load_process_mod()
    fresh = mod.execute_logic({"manifest_id": result.get("manifest_id", "")})
    st.session_state["m017_label_data"] = fresh
    return fresh


def _get_label_data(result: dict) -> dict:
    cached = st.session_state.get("m017_label_data")
    if cached and cached.get("manifest_id") == result.get("manifest_id"):
        return cached
    return _refresh(result)


def render_output(result: dict) -> None:
    if not result or result.get("error"):
        st.info("請先在 Input 頁籤確認設定，然後按下 ▶ 執行。")
        if result and result.get("error"):
            st.error(result["error"])
        return

    manifest_id = result.get("manifest_id", "")
    if not manifest_id:
        st.warning("未選擇 Manifest。")
        return

    data = _get_label_data(result)
    label_map: dict[str, list[str]] = data.get("label_map", {})
    near_dupes: list[tuple] = data.get("near_dupes", [])

    st.subheader("🏷️ Label Manager")

    # ── 摘要列 ────────────────────────────────────────────────────────────────
    m1, m2 = st.columns(2)
    m1.metric("標籤種類", len(label_map))
    total_files = sum(len(v) for v in label_map.values())
    m2.metric("涉及檔案（含重複計算）", total_files)

    # ── 近似重複警告 ────────────────────────────────────────────────────────────
    if near_dupes:
        with st.expander(f"⚠️ 發現 {len(near_dupes)} 組疑似重複標籤（可能為拼寫錯誤）", expanded=True):
            for a, b, ratio in near_dupes:
                col1, col2, col3 = st.columns([3, 3, 2])
                col1.code(a)
                col2.code(b)
                col3.caption(f"相似度 {ratio:.0%}")

    if not label_map:
        st.info("此 Manifest 尚無任何標籤。")
        return

    st.divider()

    # ── 標籤列表 + 個別操作 ────────────────────────────────────────────────────
    st.markdown("#### 標籤清單")

    labels_sorted = sorted(label_map.keys())

    for lbl in labels_sorted:
        files = label_map[lbl]
        with st.container():
            row_cols = st.columns([4, 3, 1, 1])
            row_cols[0].markdown(f"**`{lbl}`**")
            row_cols[1].caption(f"{len(files)} 個檔案")

            rename_key = f"m017_rename_new_{lbl}"
            if row_cols[2].button("✏️ 改名", key=f"m017_btn_rename_{lbl}"):
                st.session_state[f"m017_show_rename_{lbl}"] = True

            if row_cols[3].button("🗑️ 刪除", key=f"m017_btn_delete_{lbl}", type="secondary"):
                st.session_state[f"m017_confirm_delete_{lbl}"] = True

            # Rename inline form
            if st.session_state.get(f"m017_show_rename_{lbl}"):
                with st.form(key=f"m017_form_rename_{lbl}"):
                    new_name = st.text_input(
                        f"將 `{lbl}` 改名為：",
                        key=rename_key,
                        placeholder="輸入新標籤名稱",
                    )
                    fc1, fc2 = st.columns(2)
                    submitted = fc1.form_submit_button("確認改名", type="primary")
                    cancelled = fc2.form_submit_button("取消")

                if submitted and new_name.strip():
                    mod = _load_process_mod()
                    n = mod.do_rename({"manifest_id": manifest_id}, lbl, new_name.strip())
                    st.session_state.pop(f"m017_show_rename_{lbl}", None)
                    st.session_state.pop("m017_label_data", None)
                    st.success(f"已將 `{lbl}` 改名為 `{new_name.strip()}`，修改 {n} 個檔案。")
                    st.rerun()
                elif cancelled:
                    st.session_state.pop(f"m017_show_rename_{lbl}", None)
                    st.rerun()

            # Delete confirmation
            if st.session_state.get(f"m017_confirm_delete_{lbl}"):
                st.warning(
                    f"確認刪除標籤 **`{lbl}`**？\n\n"
                    f"將從 {len(files)} 個檔案中移除所有含此標籤的 shapes 及 classification。"
                )
                dc1, dc2 = st.columns(2)
                if dc1.button("⚠️ 確認刪除", key=f"m017_confirm_del_ok_{lbl}", type="primary"):
                    mod = _load_process_mod()
                    n = mod.do_delete({"manifest_id": manifest_id}, lbl)
                    st.session_state.pop(f"m017_confirm_delete_{lbl}", None)
                    st.session_state.pop("m017_label_data", None)
                    st.success(f"已刪除標籤 `{lbl}`，修改 {n} 個檔案。")
                    st.rerun()
                if dc2.button("取消", key=f"m017_confirm_del_cancel_{lbl}"):
                    st.session_state.pop(f"m017_confirm_delete_{lbl}", None)
                    st.rerun()

    # ── 合併操作 ────────────────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### 合併標籤")
    st.caption("將多個來源標籤統一改名為同一個目標標籤")

    with st.form(key="m017_form_merge"):
        sources = st.multiselect(
            "來源標籤（會被合併掉）",
            options=labels_sorted,
            key="m017_merge_sources",
        )
        target = st.selectbox(
            "目標標籤（保留）",
            options=[""] + labels_sorted,
            key="m017_merge_target",
        )
        merge_submitted = st.form_submit_button("合併", type="primary")

    if merge_submitted:
        if not sources:
            st.warning("請選擇至少一個來源標籤。")
        elif not target:
            st.warning("請選擇目標標籤。")
        else:
            real_sources = [s for s in sources if s != target]
            if not real_sources:
                st.warning("來源標籤與目標標籤相同，無需合併。")
            else:
                mod = _load_process_mod()
                n = mod.do_merge({"manifest_id": manifest_id}, real_sources, target)
                st.session_state.pop("m017_label_data", None)
                st.success(
                    f"已合併 {len(real_sources)} 個標籤 → `{target}`，共修改 {n} 個檔案。"
                )
                st.rerun()

    # ── 重新掃描按鈕 ──────────────────────────────────────────────────────────
    st.divider()
    if st.button("🔄 重新掃描標籤", key="m017_rescan"):
        st.session_state.pop("m017_label_data", None)
        st.rerun()
