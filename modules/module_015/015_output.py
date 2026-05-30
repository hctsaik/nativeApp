from __future__ import annotations

import streamlit as st


def _pct(a: int, b: int) -> float:
    if b == 0:
        return 0.0
    return a / b


def _pct_str(a: int, b: int) -> str:
    return f"{_pct(a, b) * 100:.1f}%"


def render_output(result: dict) -> None:
    mode = result.get("mode", "idle")

    if mode == "idle":
        st.info("尚未建立任何 Manifest，請先執行 **📦 Data Feeder**。")
        return

    if mode == "error":
        st.error(f"載入失敗：{result.get('error', '未知錯誤')}")
        return

    total: int = result.get("total_items", 0)
    annotated: int = result.get("annotated_xany", 0)
    classified: int = result.get("classified_count", 0)
    export_count: int = result.get("export_count", 0)
    no_json: int = result.get("no_json_count", 0)
    empty_json: int = result.get("empty_json_count", 0)
    annotated_no_class: int = result.get("annotated_no_class", 0)
    label_counts: dict = result.get("label_counts", {})
    clf_counts: dict = result.get("classification_counts", {})
    shapes_stats: dict = result.get("shapes_stats", {})
    last_annotation_at: str = result.get("last_annotation_at", "")
    export_history: list = result.get("export_history", [])
    source_path: str = result.get("source_path", "")

    # ── Manifest 標頭 ──────────────────────────────────────────────────────
    st.subheader(f"📦 {result.get('manifest_name', '—')}")
    meta_parts = []
    if source_path:
        meta_parts.append(f"📁 `{source_path}`")
    if result.get("manifest_created_at"):
        meta_parts.append(f"建立：{result['manifest_created_at']}")
    if meta_parts:
        st.caption("　｜　".join(meta_parts))

    st.divider()

    # ── 進度摘要 ───────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("總圖數", total)
    c2.metric("BBox 已標注", annotated, _pct_str(annotated, total))
    c3.metric("已分類", classified, _pct_str(classified, total))
    c4.metric("匯出次數", export_count)

    if total > 0:
        _, col_ann, col_clf, _ = st.columns(4)
        with col_ann:
            st.progress(_pct(annotated, total))
        with col_clf:
            st.progress(_pct(classified, total))

    st.divider()

    # ── 標注健康度 ─────────────────────────────────────────────────────────
    h1, h2, h3, h4 = st.columns(4)

    with h1:
        st.markdown("**最後標注時間**")
        st.markdown(last_annotation_at if last_annotation_at else "—")

    with h2:
        st.markdown("**每圖平均框數**")
        st.markdown(str(shapes_stats["mean"]) if shapes_stats else "—")

    with h3:
        st.markdown("**框數範圍**")
        if shapes_stats:
            st.markdown(f"{shapes_stats['min']} – {shapes_stats['max']}")
        else:
            st.markdown("—")

    with h4:
        st.markdown("**尚未標注**")
        unannotated = no_json + empty_json
        color = "red" if unannotated > 0 else "green"
        st.markdown(f":{color}[**{unannotated} 張**]")

    # 警告提示
    if annotated_no_class > 0 and clf_counts:
        st.warning(
            f"⚠️ **{annotated_no_class}** 張圖片已有 BBox 標注但尚未分類，"
            "匯出 ImageFolder / CSV 時分類欄位會留空。"
        )

    if no_json > 0 and annotated == 0:
        st.info(
            f"尚有 **{total}** 張圖片未開始標注，"
            "請切換到 **🏷️ Annotation** 頁籤進行標注。"
        )
    elif no_json > 0:
        st.info(f"還有 **{no_json}** 張圖片尚未標注。")

    st.divider()

    # ── 標籤分布 ───────────────────────────────────────────────────────────
    col_bbox, col_clf = st.columns(2)

    with col_bbox:
        st.subheader("BBox 標籤分布")
        if label_counts:
            sorted_lbl = dict(sorted(label_counts.items(), key=lambda x: -x[1]))
            st.bar_chart(sorted_lbl, x_label="標籤", y_label="框數")
            total_boxes = sum(label_counts.values())
            st.caption(f"共 {len(label_counts)} 種標籤，{total_boxes} 個框")
        else:
            st.caption("無 BBox 標注資料")

    with col_clf:
        st.subheader("分類標籤分布")
        if clf_counts:
            sorted_clf = dict(sorted(clf_counts.items(), key=lambda x: -x[1]))
            st.bar_chart(sorted_clf, x_label="分類", y_label="張數")
            st.caption(f"共 {len(clf_counts)} 種分類")
        else:
            st.caption("無分類資料（module_012 尚未執行）")

    st.divider()

    # ── 匯出記錄 ───────────────────────────────────────────────────────────
    st.subheader("匯出記錄")
    if export_history:
        sorted_exports = sorted(
            export_history,
            key=lambda x: x.get("created_at", ""),
            reverse=True,
        )
        latest = sorted_exports[0]
        st.markdown(
            f"**最近一次**：`{latest.get('export_format', '')}` 　"
            f"｜　{latest.get('item_count', 0)} 張　"
            f"｜　{(latest.get('created_at') or '')[:19]}"
        )
        if latest.get("export_path"):
            st.caption(f"📁 `{latest['export_path']}`")

        if len(sorted_exports) > 1:
            with st.expander(f"查看全部 {len(sorted_exports)} 筆記錄"):
                st.dataframe(
                    [
                        {
                            "格式": ex.get("export_format", ""),
                            "數量": ex.get("item_count", 0),
                            "時間": (ex.get("created_at") or "")[:19],
                            "路徑": ex.get("export_path", ""),
                        }
                        for ex in sorted_exports
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
    else:
        st.caption("尚無匯出記錄")
