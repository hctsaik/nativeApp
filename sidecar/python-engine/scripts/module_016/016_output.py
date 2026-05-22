from __future__ import annotations

import streamlit as st


def render_output(result: dict) -> None:
    mode = result.get("mode", "idle")

    if mode == "idle":
        st.info(
            "選擇模型與參數後按「▶ 執行」。\n\n"
            "推論結果會直接寫成 X-AnyLabeling `.json` 檔案，"
            "完成後可切換到 **Annotation** 頁籤開啟 X-AnyLabeling 修正標注。"
        )
        return

    if mode == "error":
        st.error(f"執行失敗：{result.get('error', '未知錯誤')}")
        return

    # ── 摘要 ──────────────────────────────────────────────────────────────────
    st.success("推論完成！")

    total = result.get("total_items", 0)
    ok = result.get("ok", 0)
    skipped = result.get("skipped", 0)
    errors = result.get("errors", 0)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("總圖數", total)
    c2.metric("✅ 成功推論", ok)
    c3.metric("⏭️ 跳過", skipped, help="已有標注且未勾選覆蓋，或信心分數不足")
    c4.metric("❌ 錯誤", errors)

    model_type = result.get("model_type", "yolo")
    started_at = result.get("started_at", "")
    st.caption(
        f"模式：{'YOLO Detection' if model_type == 'yolo' else 'Image Classifier'}　"
        f"｜　執行時間：{started_at}"
    )

    if ok > 0:
        st.info(
            f"已對 **{ok}** 張圖片寫入預標注結果。\n\n"
            "切換到 **🏷️ Annotation** 頁籤，點選「開啟 X-AnyLabeling」即可逐張修正。"
        )

    st.divider()

    # ── 詳細結果 ──────────────────────────────────────────────────────────────
    item_results: list[dict] = result.get("item_results", [])
    if not item_results:
        return

    # 統計各狀態數量
    status_counts: dict[str, int] = {}
    for it in item_results:
        s = it.get("status", "")
        status_counts[s] = status_counts.get(s, 0) + 1

    filter_options = ["全部"] + sorted(status_counts.keys())
    selected_filter = st.selectbox(
        "篩選狀態",
        filter_options,
        format_func=lambda s: {
            "全部": f"全部（{len(item_results)}）",
            "ok": f"✅ 成功（{status_counts.get('ok', 0)}）",
            "skipped": f"⏭️ 跳過（{status_counts.get('skipped', 0)}）",
            "low_conf": f"🟡 信心不足（{status_counts.get('low_conf', 0)}）",
            "error": f"❌ 錯誤（{status_counts.get('error', 0)}）",
        }.get(s, s),
        key="m016_filter",
    )

    filtered = item_results if selected_filter == "全部" else [
        r for r in item_results if r.get("status") == selected_filter
    ]

    # 分頁
    PAGE = 100
    n_pages = max(1, (len(filtered) + PAGE - 1) // PAGE)
    if "m016_page" not in st.session_state:
        st.session_state["m016_page"] = 0
    page = min(st.session_state["m016_page"], n_pages - 1)

    if n_pages > 1:
        col_l, col_m, col_r = st.columns([1, 3, 1])
        with col_l:
            if st.button("◀", disabled=(page == 0), key="m016_prev"):
                st.session_state["m016_page"] = page - 1
                st.rerun()
        with col_m:
            st.markdown(
                f"<div style='text-align:center;padding-top:6px'>"
                f"第 {page+1} / {n_pages} 頁</div>",
                unsafe_allow_html=True,
            )
        with col_r:
            if st.button("▶", disabled=(page >= n_pages - 1), key="m016_next"):
                st.session_state["m016_page"] = page + 1
                st.rerun()

    page_rows = filtered[page * PAGE: (page + 1) * PAGE]
    st.dataframe(
        [{"檔名": r["file"], "狀態": r["status"], "說明": r["detail"]} for r in page_rows],
        use_container_width=True,
        hide_index=True,
    )
