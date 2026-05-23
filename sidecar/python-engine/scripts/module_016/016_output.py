from __future__ import annotations

import importlib.util
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent
_cfg_spec = importlib.util.spec_from_file_location("_016_config", _HERE / "_config.py")
_cfg = importlib.util.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)


def _show_progress_panel() -> bool:
    """Read progress file and render live progress. Returns True if job is running."""
    prog = _cfg.read_progress()
    if prog is None:
        return False

    running: bool = prog.get("running", False)
    done: int = prog.get("done", 0)
    total: int = prog.get("total", 0)
    ok: int = prog.get("ok", 0)
    skipped: int = prog.get("skipped", 0)
    errors: int = prog.get("errors", 0)
    current: str = prog.get("current", "")
    started_at: str = prog.get("started_at", "")

    if running:
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=2000, key="m016_live_refresh")
        except ImportError:
            pass

        st.subheader("⚙️ 推論進行中…")
        ratio = done / total if total > 0 else 0
        st.progress(ratio, text=f"{done} / {total} 張　（{ratio:.1%}）")

        if current:
            st.caption(f"正在處理：`{current}`")

        c1, c2, c3 = st.columns(3)
        c1.metric("✅ 成功", ok)
        c2.metric("⏭️ 跳過", skipped)
        c3.metric("❌ 錯誤", errors)
        st.caption(f"開始時間：{started_at}")
        return True

    return False


def render_output(result: dict) -> None:
    mode = result.get("mode", "idle")

    # 優先顯示 live 進度（mode=idle 表示上一次 result 還沒更新）
    if mode == "idle":
        if _show_progress_panel():
            return
        st.info(
            "選擇模型與參數後按「▶ 執行」。\n\n"
            "推論結果會直接寫成 X-AnyLabeling `.json` 檔案，"
            "完成後可切換到 **Annotation** 頁籤開啟 X-AnyLabeling 修正標注。"
        )
        return

    if mode == "error":
        st.error(f"執行失敗：{result.get('error', '未知錯誤')}")
        return

    # mode == "done" — 先確認是否還有 running 進度（極少發生，防呆）
    _show_progress_panel()

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
