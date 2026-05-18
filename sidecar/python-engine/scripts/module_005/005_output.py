from __future__ import annotations

import base64
import csv
import io
import os
import sqlite3
from pathlib import Path

import streamlit as st

_COLS    = [0.9, 1.7, 0.8, 0.7, 0.8, 0.8, 0.7, 0.7, 0.7, 0.7, 1.2, 1.5, 0.5, 0.4]
_HEADERS = [
    "Parts", "影像檔名（點擊預覽）",
    "貼合偏移", "重合度", "平均偏差(px)", "偏差方向",
    "左粗糙", "右粗糙", "頻率", "強度",
    "尺寸", "時間戳記", "下載", "刪除",
]


def _db_path() -> Path:
    return Path(os.environ.get("CIM_LOG_DIR", "/tmp")) / "edge_records.sqlite"


def _delete_record(record_id: int) -> None:
    with sqlite3.connect(_db_path()) as conn:
        conn.execute("DELETE FROM edge_records WHERE id = ?", (record_id,))


def _records_to_csv(records: list[dict]) -> str:
    fields = [
        "id", "parts", "image_name",
        "left_roughness", "right_roughness",
        "frequency", "intensity",
        "image_width", "image_height",
        "gradient_dir_variance", "psd_energy_ratio",
        "fit_overall", "fit_offset_score", "fit_left", "fit_right",
        "fit_avg_dist", "fit_avg_signed_dist",
        "fit_left_signed_dist", "fit_right_signed_dist",
        "timestamp",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(records)
    return buf.getvalue()


@st.dialog("影像預覽", width="large")
def _show_preview(rec: dict) -> None:
    image_bytes = base64.b64decode(rec["image_b64"]) if rec.get("image_b64") else None
    fname  = rec.get("image_name") or "image.png"
    orig_w = rec.get("image_width", 0)
    orig_h = rec.get("image_height", 0)

    st.caption(f"{fname}　·　{orig_w} × {orig_h} px")

    if image_bytes:
        st.image(image_bytes, width=orig_w if orig_w > 0 else None)
        st.download_button(
            "下載原圖",
            data=image_bytes,
            file_name=fname,
            mime="image/png",
            icon=":material/cloud_download:",
            key=f"dlg_dl_{rec['id']}",
        )
    else:
        st.info("無影像資料")

    st.divider()
    指標_list = []
    數值_list = []
    if rec.get("fit_overall") is not None:
        指標_list += [
            "貼合偏移",
            "重合度",
            "左側貼合度",
            "右側貼合度",
            "平均偏差(px)",
            "左側偏差",
            "右側偏差",
        ]
        數值_list += [
            _offset_label(rec.get("fit_offset_score")),
            rec["fit_overall"],
            rec["fit_left"],
            rec["fit_right"],
            rec.get("fit_avg_dist"),
            _signed_label(rec.get("fit_left_signed_dist")),
            _signed_label(rec.get("fit_right_signed_dist")),
        ]
    gdv = rec.get("gradient_dir_variance")
    psd = rec.get("psd_energy_ratio")
    指標_list += ["左粗糙度", "右粗糙度", "頻率", "強度", "梯度方向變異", "PSD 高頻能量比"]
    數值_list += [
        rec["left_roughness"], rec["right_roughness"],
        rec["frequency"],      rec["intensity"],
        gdv if gdv is not None else "—",
        psd if psd is not None else "—",
    ]
    st.table({"指標": 指標_list, "數值": 數值_list})


def _signed_label(value: float | None) -> str:
    if value is None:
        return "—"
    direction = "內縮" if value > 0 else ("突出" if value < 0 else "貼齊")
    return f"{value:+.2f} px（{direction}）"


def _offset_label(value: float | None) -> str:
    if value is None:
        return "—"
    direction = "內縮" if value < 0 else ("外突" if value > 0 else "重合")
    return f"{value:+.3f}（{direction}）"


def _direction_label(value: float | None) -> str:
    if value is None:
        return "—"
    if value < 0:
        return "內縮"
    if value > 0:
        return "外突"
    return "重合"


def _header_row() -> None:
    for col, label in zip(st.columns(_COLS), _HEADERS):
        col.markdown(f"**{label}**")
    st.divider()


def _data_row(rec: dict, deleted_ids: set) -> None:
    cols = st.columns(_COLS)

    cols[0].write(rec["parts"] or "—")

    fname = rec.get("image_name") or "（無檔名）"
    if cols[1].button(fname, key=f"view_{rec['id']}"):
        _show_preview(rec)

    fit = rec.get("fit_overall")
    offset_score = rec.get("fit_offset_score")
    if fit is not None:
        avg_dist = rec.get("fit_avg_dist")
        cols[2].write(f"{offset_score:+.3f}" if offset_score is not None else "—")
        cols[3].write(f"{fit:.3f}")
        cols[4].write(f"{avg_dist:.1f}" if avg_dist is not None else "—")
        cols[5].write(_direction_label(offset_score))
    else:
        cols[2].write("—")
        cols[3].write("—")
        cols[4].write("—")
        cols[5].write("—")

    cols[6].write(rec["left_roughness"])
    cols[7].write(rec["right_roughness"])
    cols[8].write(rec["frequency"])
    cols[9].write(rec["intensity"])

    cols[10].write(f"{rec['image_width']} × {rec['image_height']}")
    cols[11].write(rec["timestamp"])

    image_bytes = base64.b64decode(rec["image_b64"]) if rec.get("image_b64") else None
    if image_bytes:
        cols[12].download_button(
            "",
            data=image_bytes,
            file_name=fname if fname != "（無檔名）" else "image.png",
            mime="image/png",
            icon=":material/image:",
            key=f"dl_{rec['id']}",
        )
    else:
        cols[12].write("—")

    if cols[13].button("🗑️", key=f"del_{rec['id']}", help="刪除此筆記錄"):
        _delete_record(rec["id"])
        deleted_ids.add(rec["id"])
        st.toast(f"已刪除記錄 #{rec['id']}", icon=":material/delete:")
        st.rerun()

    st.divider()


def _filter_summary(filters: dict) -> str:
    parts = filters.get("parts") or []
    kw    = filters.get("image_name_kw", "")
    l_min, l_max = filters.get("left_min", 0), filters.get("left_max", 9999)
    r_min, r_max = filters.get("right_min", 0), filters.get("right_max", 9999)
    tags = []
    if parts:
        tags.append(f"料號：{', '.join(parts)}")
    if kw:
        tags.append(f"檔名含「{kw}」")
    if l_min > 0 or l_max < 9999:
        tags.append(f"左粗糙 {l_min:.3f}～{l_max:.3f}")
    if r_min > 0 or r_max < 9999:
        tags.append(f"右粗糙 {r_min:.3f}～{r_max:.3f}")
    return "、".join(tags) if tags else ""


def render_output(result: dict) -> None:
    if result.get("error") == "no_date":
        st.warning("請選擇量測日期區間後再執行。")
        return
    if result.get("error") == "no_db":
        st.warning("尚無資料庫，請先使用「邊緣完整度偵測」模組儲存資料。")
        return

    records:   list[dict] = result.get("records", [])
    date_from: str        = result.get("date_from", "")
    date_to:   str        = result.get("date_to", "")
    filters:   dict       = result.get("filters", {})

    st.subheader(f"量測記錄 — {date_from} ～ {date_to}")

    summary = _filter_summary(filters)
    if summary:
        st.caption(f"篩選條件：{summary}")

    if not records:
        st.info("該條件下無任何記錄。")
        return

    # session_state 追蹤本次已刪除的 id（避免重新執行才消失）
    if "deleted_ids" not in st.session_state:
        st.session_state.deleted_ids = set()

    visible = [r for r in records if r["id"] not in st.session_state.deleted_ids]

    col_count, col_csv, col_del_all = st.columns([3, 2, 2])
    col_count.caption(f"共 {len(visible)} 筆")

    # Export CSV
    if visible:
        csv_data = _records_to_csv(visible)
        col_csv.download_button(
            "📥 匯出 CSV",
            data=csv_data.encode("utf-8-sig"),
            file_name=f"edge_{date_from}_{date_to}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    # 批次刪除目前所有可見記錄
    if visible and col_del_all.button("🗑️ 刪除全部", use_container_width=True, type="secondary"):
        st.session_state["confirm_delete_all"] = True

    if st.session_state.get("confirm_delete_all"):
        st.warning(f"⚠️ 確定要刪除這 {len(visible)} 筆記錄？此操作無法復原。")
        c1, c2, _ = st.columns([1, 1, 4])
        if c1.button("確認刪除", type="primary", key="confirm_yes"):
            for rec in visible:
                _delete_record(rec["id"])
                st.session_state.deleted_ids.add(rec["id"])
            st.session_state["confirm_delete_all"] = False
            st.toast(f"已刪除 {len(visible)} 筆記錄", icon=":material/delete:")
            st.rerun()
        if c2.button("取消", key="confirm_no"):
            st.session_state["confirm_delete_all"] = False
            st.rerun()
        return

    if not visible:
        st.info("所有記錄已刪除。")
        return

    _header_row()
    for rec in visible:
        _data_row(rec, st.session_state.deleted_ids)
