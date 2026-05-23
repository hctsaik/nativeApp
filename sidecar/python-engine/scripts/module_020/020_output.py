from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_020_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_proc_spec = _ilu.spec_from_file_location("_020_process", _HERE / "020_process.py")
_proc = _ilu.module_from_spec(_proc_spec)
_proc_spec.loader.exec_module(_proc)

_help_spec = _ilu.spec_from_file_location("_help", _HERE.parent / "shared" / "_help.py")
_help = _ilu.module_from_spec(_help_spec)
_help_spec.loader.exec_module(_help)


def _status_badge(status: str) -> str:
    return {"accepted": "✅ 已接受", "pending": "⏳ 處理中", "failed": "❌ 失敗"}.get(status, status)


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n/1024:.1f} KB"
    return f"{n/1024**2:.1f} MB"


def _do_query(params: dict, page: int) -> dict:
    query_params = {**params, "page": page, "page_size": _cfg.PAGE_SIZE}
    return _proc.list_submissions(query_params)


def render_output(result: dict) -> None:
    _help.render_help_button("module_020", "output")
    mode = result.get("mode", "idle")

    # ── 下載完成結果（由 EXECUTE 觸發後寫入 session）────────────────────────────
    dl_result = st.session_state.get("m020_download_result")
    if dl_result:
        if dl_result.get("mode") == "done":
            extract_dir = dl_result.get("extract_dir", "")
            size = dl_result.get("size_bytes", 0)
            st.success(f"✅ 下載完成　{_fmt_size(size)}")
            st.info(f"📁 `{extract_dir}`")

            if st.button("→ 送至 Data Feeder", key="m020_send_to_feeder"):
                _cfg.write_shared_suggested_folder(extract_dir)
                st.success("已寫入 Data Feeder 路徑，請切換至 📦 Data Feeder 頁籤。")

        elif dl_result.get("mode") == "warn":
            st.warning(dl_result.get("error", ""))
            st.info(f"原始 ZIP：`{dl_result.get('zip_path', '')}`")
        else:
            st.error(dl_result.get("error", "下載失敗"))

        if st.button("🔄 清除下載結果", key="m020_clear_dl"):
            st.session_state.pop("m020_download_result", None)
            st.rerun()

        st.divider()

    # ── 查詢觸發 ──────────────────────────────────────────────────────────────
    if mode == "idle":
        st.info("請在左側設定查詢條件，然後按下 ▶ 執行查詢。")
        return

    if mode == "error":
        st.error(result.get("error", "未知錯誤"))
        return

    # ── mode = "query_result"（由 EXECUTE 後 output 解讀 params 自行 query） ────
    # 實際上 execute_logic 在本模組負責下載，查詢由 output 主動呼叫。
    # 但 portal 的 EXECUTE_COMPLETE 會把 result 傳到這裡；
    # 若 result 中有 submit_id，代表是下載結果，否則代表查詢觸發。

    if result.get("submit_id"):
        # 這是下載結果，不走查詢 UI
        return

    # ── 查詢結果展示 ──────────────────────────────────────────────────────────
    query_params: dict = st.session_state.get("m020_query_params", {})
    if not query_params:
        query_params = {k: result.get(k, "") for k in
                        ("service_url", "nt_account", "system_name", "data_type", "date_from", "date_to")}

    if "m020_page" not in st.session_state:
        st.session_state["m020_page"] = 1

    page = st.session_state["m020_page"]
    qr = _do_query(query_params, page)

    if qr.get("mode") == "error":
        st.error(qr.get("error", "查詢失敗"))
        return

    total: int = qr.get("total", 0)
    items: list[dict] = qr.get("items", [])
    total_pages = max(1, (total + _cfg.PAGE_SIZE - 1) // _cfg.PAGE_SIZE)

    st.markdown(f"**查詢結果　共 {total} 筆**")

    if not items:
        st.info("查無符合條件的上傳記錄，請調整篩選條件（系統名稱、日期範圍）後重新查詢。")
        return

    # ── Radio 選單 ────────────────────────────────────────────────────────────
    radio_labels = []
    radio_ids = []
    for it in items:
        ts = (it.get("timestamp") or "")[:16]
        sys_dt = f"{it.get('system_name', '')} / {it.get('data_type', '')}"
        cnt = it.get("item_count", 0)
        badge = _status_badge(it.get("status", ""))
        desc = it.get("description", "")
        label = f"{ts}　｜　{sys_dt}　｜　{cnt} 張　｜　{badge}"
        if desc:
            label += f"　｜　{desc[:40]}"
        radio_labels.append(label)
        radio_ids.append(it.get("submit_id", ""))

    selected_idx = st.radio(
        "選取要下載的批次",
        range(len(radio_labels)),
        format_func=lambda i: radio_labels[i],
        key="m020_radio_select",
    )
    selected_id = radio_ids[selected_idx] if radio_ids else ""
    selected_item = items[selected_idx] if items else {}
    selected_status = selected_item.get("status", "")

    # 把選取的 submit_id 存回 session，讓 input 能讀到（作為 EXECUTE 參數）
    st.session_state["m020_selected_submit_id"] = selected_id
    st.session_state["m020_query_params"] = query_params

    # ── Download 按鈕 ─────────────────────────────────────────────────────────
    download_disabled = selected_status == "failed" or not selected_id
    btn_help = "此批次上傳失敗，無法下載" if selected_status == "failed" else None

    if st.button(
        "⬇ Download 選取的批次",
        disabled=download_disabled,
        help=btn_help,
        type="primary",
        key="m020_download_btn",
    ):
        with st.spinner(f"下載中… submit_id: {selected_id[:8]}…"):
            dl_params = {
                "service_url": query_params.get("service_url", ""),
                "nt_account": query_params.get("nt_account", ""),
                "submit_id": selected_id,
            }
            dl_r = _proc.execute_logic(dl_params)
        st.session_state["m020_download_result"] = dl_r
        st.rerun()

    # ── 分頁控制 ──────────────────────────────────────────────────────────────
    if total_pages > 1:
        st.divider()
        pc1, pc2, pc3 = st.columns([1, 3, 1])
        with pc1:
            if st.button("◀ 上一頁", disabled=page <= 1, key="m020_prev"):
                st.session_state["m020_page"] = page - 1
                st.rerun()
        with pc2:
            st.markdown(f"<center>第 {page} / {total_pages} 頁</center>", unsafe_allow_html=True)
        with pc3:
            if st.button("下一頁 ▶", disabled=page >= total_pages, key="m020_next"):
                st.session_state["m020_page"] = page + 1
                st.rerun()
