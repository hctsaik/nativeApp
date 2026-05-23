from __future__ import annotations

import importlib.util
import importlib.util as _ilu
import json
import os
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent
_PROCESS_FILE = _HERE / "017_process.py"

_mdb_spec = _ilu.spec_from_file_location(
    "_manifest_db_017", _HERE.parent / "shared" / "_manifest_db.py"
)
_mdb = _ilu.module_from_spec(_mdb_spec)
_mdb_spec.loader.exec_module(_mdb)

_help_spec = _ilu.spec_from_file_location("_help", _HERE.parent / "shared" / "_help.py")
_help = _ilu.module_from_spec(_help_spec)
_help_spec.loader.exec_module(_help)

_CIM_LOG_DIR = Path(os.environ.get(
    "CIM_LOG_DIR", str(Path(__file__).resolve().parents[4] / "tmp" / "cim_log")
))


def _load_process_mod():
    spec = importlib.util.spec_from_file_location("_017_process", _PROCESS_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _refresh(result: dict) -> dict:
    mod = _load_process_mod()
    fresh = mod.execute_logic({"manifest_id": result.get("manifest_id", "")})
    st.session_state["m017_label_data"] = fresh
    return fresh


def _get_data(result: dict) -> dict:
    cached = st.session_state.get("m017_label_data")
    if cached and cached.get("manifest_id") == result.get("manifest_id"):
        return cached
    return _refresh(result)


# ── Dashboard helpers ─────────────────────────────────────────────────────────

def _pct(a: int, b: int) -> float:
    return a / b if b else 0.0


def _pct_str(a: int, b: int) -> str:
    return f"{_pct(a, b) * 100:.1f}%"


def _render_dashboard(data: dict) -> None:
    total: int = data.get("total_items", 0)
    annotated: int = data.get("annotated_xany", 0)
    classified: int = data.get("classified_count", 0)
    export_count: int = data.get("export_count", 0)
    no_json: int = data.get("no_json_count", 0)
    empty_json: int = data.get("empty_json_count", 0)
    annotated_no_class: int = data.get("annotated_no_class", 0)
    label_counts: dict = data.get("label_counts", {})
    clf_counts: dict = data.get("classification_counts", {})
    shapes_stats: dict = data.get("shapes_stats", {})
    last_annotation_at: str = data.get("last_annotation_at", "")
    export_history: list = data.get("export_history", [])
    source_path: str = data.get("source_path", "")

    # Manifest 標頭
    st.subheader(f"📦 {data.get('manifest_name', '—')}")
    meta_parts = []
    if source_path:
        meta_parts.append(f"📁 `{source_path}`")
    if data.get("manifest_created_at"):
        meta_parts.append(f"建立：{data['manifest_created_at']}")
    if meta_parts:
        st.caption("　｜　".join(meta_parts))

    st.divider()

    # 進度摘要
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

    # 標注健康度
    h1, h2, h3, h4 = st.columns(4)
    with h1:
        st.markdown("**最後標注時間**")
        st.markdown(last_annotation_at if last_annotation_at else "—")
    with h2:
        st.markdown("**每圖平均框數**")
        st.markdown(str(shapes_stats["mean"]) if shapes_stats else "—")
    with h3:
        st.markdown("**框數範圍**")
        st.markdown(f"{shapes_stats['min']} – {shapes_stats['max']}" if shapes_stats else "—")
    with h4:
        st.markdown("**尚未標注**")
        unannotated = no_json + empty_json
        color = "red" if unannotated > 0 else "green"
        st.markdown(f":{color}[**{unannotated} 張**]")

    if annotated_no_class > 0 and clf_counts:
        st.warning(
            f"⚠️ **{annotated_no_class}** 張圖片已有 BBox 標注但尚未分類，"
            "匯出 ImageFolder / CSV 時分類欄位會留空。"
        )
    if no_json > 0 and annotated == 0:
        st.info(f"尚有 **{total}** 張圖片未開始標注，請切換到 **🏷️ Annotation** 頁籤。")
    elif no_json > 0:
        st.info(f"還有 **{no_json}** 張圖片尚未標注。")

    st.divider()

    # 標籤分布
    col_bbox, col_clf = st.columns(2)
    with col_bbox:
        st.subheader("BBox 標籤分布")
        if label_counts:
            st.bar_chart(
                dict(sorted(label_counts.items(), key=lambda x: -x[1])),
                x_label="標籤", y_label="框數",
            )
            st.caption(f"共 {len(label_counts)} 種標籤，{sum(label_counts.values())} 個框")
        else:
            st.caption("無 BBox 標注資料")
    with col_clf:
        st.subheader("分類標籤分布")
        if clf_counts:
            st.bar_chart(
                dict(sorted(clf_counts.items(), key=lambda x: -x[1])),
                x_label="分類", y_label="張數",
            )
            st.caption(f"共 {len(clf_counts)} 種分類")
        else:
            st.caption("無分類資料")

    st.divider()

    # 匯出記錄
    st.subheader("匯出記錄")
    if export_history:
        sorted_exports = sorted(export_history, key=lambda x: x.get("created_at", ""), reverse=True)
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
                    [{"格式": ex.get("export_format", ""), "數量": ex.get("item_count", 0),
                      "時間": (ex.get("created_at") or "")[:19], "路徑": ex.get("export_path", "")}
                     for ex in sorted_exports],
                    use_container_width=True, hide_index=True,
                )
    else:
        st.caption("尚無匯出記錄")

    # ── QA Review 統計 ────────────────────────────────────────────────────────
    st.divider()
    st.subheader("🔍 QA Review 統計")
    manifest_id: str = data.get("manifest_id", "")
    _render_review_summary(manifest_id)

    # ── 最後同步記錄（module_013）─────────────────────────────────────────────
    st.divider()
    st.subheader("同步至 Service")
    _render_last_sync(manifest_id)


def _render_review_summary(manifest_id: str) -> None:
    """Read .review.json sidecars for all items and show QA stats."""
    db_path = _CIM_LOG_DIR / "db" / "manifest.sqlite"
    cache_key = f"m017_review_{manifest_id}"
    cached = st.session_state.get(cache_key)

    if cached is None:
        try:
            items = _mdb.get_manifest_items(db_path, manifest_id)
        except Exception:
            items = []

        approved = rejected = pending = 0
        reviewer_counts: dict[str, int] = {}
        comments: list[dict] = []

        for it in items:
            fp = it.get("file_path", "")
            if not fp:
                pending += 1
                continue
            rev_path = Path(fp).parent / (Path(fp).name + ".review.json")
            if rev_path.exists():
                try:
                    rev = json.loads(rev_path.read_text(encoding="utf-8"))
                    rev_st = rev.get("status", "pending")
                    if rev_st == "approved":
                        approved += 1
                    elif rev_st == "rejected":
                        rejected += 1
                    else:
                        pending += 1
                    rv = rev.get("reviewer", "")
                    if rv:
                        reviewer_counts[rv] = reviewer_counts.get(rv, 0) + 1
                    if rev.get("comment") and rev_st == "rejected":
                        comments.append({
                            "file": Path(fp).name,
                            "comment": rev["comment"],
                            "timestamp": (rev.get("timestamp") or "")[:19],
                        })
                except Exception:
                    pending += 1
            else:
                pending += 1

        cached = {
            "approved": approved,
            "rejected": rejected,
            "pending": pending,
            "total": len(items),
            "reviewer_counts": reviewer_counts,
            "rejected_comments": comments,
        }
        st.session_state[cache_key] = cached

    total = cached["total"]
    approved = cached["approved"]
    rejected = cached["rejected"]
    pending = cached["pending"]

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("總計", total)
    r2.metric("✅ 核准", approved)
    r3.metric("❌ 退回", rejected)
    r4.metric("⏳ 待審", pending)

    if total > 0:
        _, col_a, col_r, _ = st.columns(4)
        with col_a:
            st.progress(approved / total if total else 0)
        with col_r:
            st.progress(rejected / total if total else 0)

    if cached["reviewer_counts"]:
        st.caption("審核人：" + "　".join(
            f"{rv}（{cnt}）" for rv, cnt in cached["reviewer_counts"].items()
        ))

    if cached["rejected_comments"]:
        with st.expander(f"❌ 退回備註（{len(cached['rejected_comments'])} 筆）"):
            for c in cached["rejected_comments"]:
                st.markdown(f"**`{c['file']}`** — {c['comment']} `{c['timestamp']}`")

    if st.button("🔄 重新統計 QA", key="m017_refresh_qa"):
        st.session_state.pop(cache_key, None)
        st.rerun()


def _render_last_sync(manifest_id: str) -> None:
    try:
        _cfg013_spec = _ilu.spec_from_file_location(
            "_013_config",
            Path(__file__).resolve().parents[1] / "module_013" / "_config.py",
        )
        _cfg013 = _ilu.module_from_spec(_cfg013_spec)
        _cfg013_spec.loader.exec_module(_cfg013)
        entries = _cfg013.read_sync_history(manifest_id, limit=10)
    except Exception:
        entries = []

    if not entries:
        st.caption("尚無同步記錄。完成標注後請至 **🔄 Sync Back** 頁籤送出。")
        return

    last = entries[-1]
    started = last.get("started_at", "")[:19].replace("T", " ")
    status_label = {"ok": "✅ 完全成功", "partial_fail": "⚠️ 部分失敗", "fail": "❌ 全部失敗"}.get(
        last.get("status", ""), last.get("status", "")
    )
    fmts = ", ".join(last.get("formats", [])) or "無"
    sys_info = f"{last.get('system_name', '')} / {last.get('data_type', '')}" if last.get("system_name") else ""
    st.markdown(
        f"**最近一次**：{started}"
        + (f"　｜　{sys_info}" if sys_info else "")
        + f"　｜　scope: {last.get('scope', '')}　"
        f"｜　{last.get('ok_count', 0)} / {last.get('scope_count', 0)} 筆成功　"
        f"｜　格式: {fmts}　｜　{status_label}"
    )

    if len(entries) > 1:
        with st.expander(f"查看全部 {len(entries)} 筆記錄"):
            rows = []
            for e in reversed(entries):
                rows.append({
                    "時間": (e.get("started_at") or "")[:19].replace("T", " "),
                    "系統": e.get("system_name", ""),
                    "資料類型": e.get("data_type", ""),
                    "送出者": e.get("nt_account", ""),
                    "scope": e.get("scope", ""),
                    "成功/總計": f"{e.get('ok_count', 0)} / {e.get('scope_count', 0)}",
                    "格式": ", ".join(e.get("formats", [])) or "無",
                    "狀態": {"ok": "✅", "partial_fail": "⚠️", "fail": "❌"}.get(e.get("status", ""), ""),
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)


# ── Label Manager ─────────────────────────────────────────────────────────────

def _render_label_manager(manifest_id: str, data: dict) -> None:
    label_map: dict[str, list[str]] = data.get("label_map", {})
    near_dupes: list[tuple] = data.get("near_dupes", [])

    # 摘要列
    m1, m2 = st.columns(2)
    m1.metric("標籤種類", len(label_map))
    m2.metric("涉及檔案（含重複計算）", sum(len(v) for v in label_map.values()))

    # 近似重複警告
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

    # 標籤列表 + 個別操作
    st.markdown("#### 標籤清單")
    labels_sorted = sorted(label_map.keys())

    for lbl in labels_sorted:
        files = label_map[lbl]
        with st.container():
            row_cols = st.columns([4, 3, 1, 1])
            row_cols[0].markdown(f"**`{lbl}`**")
            row_cols[1].caption(f"{len(files)} 個檔案")

            if row_cols[2].button("✏️ 改名", key=f"m017_btn_rename_{lbl}"):
                st.session_state[f"m017_show_rename_{lbl}"] = True

            if row_cols[3].button("🗑️ 刪除", key=f"m017_btn_delete_{lbl}", type="secondary"):
                st.session_state[f"m017_confirm_delete_{lbl}"] = True

            if st.session_state.get(f"m017_show_rename_{lbl}"):
                with st.form(key=f"m017_form_rename_{lbl}"):
                    new_name = st.text_input(
                        f"將 `{lbl}` 改名為：",
                        key=f"m017_rename_new_{lbl}",
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

    # 合併操作
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
                st.success(f"已合併 {len(real_sources)} 個標籤 → `{target}`，共修改 {n} 個檔案。")
                st.rerun()

    # 重新掃描
    st.divider()
    if st.button("🔄 重新掃描", key="m017_rescan"):
        st.session_state.pop("m017_label_data", None)
        st.rerun()


# ── 主進入點 ──────────────────────────────────────────────────────────────────

def render_output(result: dict) -> None:
    _help.render_help_button("module_017", "output")
    if not result or result.get("error"):
        st.info("請先在 Input 頁籤確認設定，然後按下 ▶ 執行。")
        if result and result.get("error"):
            st.error(result["error"])
        return

    manifest_id = result.get("manifest_id", "")
    if not manifest_id:
        st.warning("未選擇 Manifest。")
        return

    data = _get_data(result)

    tab_dash, tab_labels = st.tabs(["📊 統計總覽", "🏷️ 標籤管理"])

    with tab_dash:
        _render_dashboard(data)

    with tab_labels:
        _render_label_manager(manifest_id, data)
