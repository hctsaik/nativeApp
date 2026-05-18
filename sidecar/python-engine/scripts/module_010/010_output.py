from __future__ import annotations

import base64
import csv
import importlib.util as _ilu
import io
import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

# ─── 動態載入 _manifest_db + _config ─────────────────────────────────────────

_HERE = Path(__file__).resolve().parent

_mdb_spec = _ilu.spec_from_file_location(
    "_manifest_db", _HERE.parent / "shared" / "_manifest_db.py"
)
_mdb = _ilu.module_from_spec(_mdb_spec)
_mdb_spec.loader.exec_module(_mdb)

_cfg_spec = _ilu.spec_from_file_location("_010_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CIM_LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", str(_PROJECT_ROOT / "tmp" / "cim_log")))

_SOURCE_LABEL = {"folder": "📁 資料夾", "db": "🗄️ 資料庫", "api": "🌐 API"}


def _post_message(msg_type: str, payload: dict) -> None:
    import json as _json
    blob = _json.dumps({"type": msg_type, "source": "cim-platform", "payload": payload, "_cim": True})
    components.html(f"<script>window.top.postMessage({blob}, '*');</script>", height=0)

# ─── 影像編碼（快取到 session，避免重複 IO） ───────────────────────────────────

@st.cache_data(show_spinner=False, max_entries=2000)
def _encode_item(file_path: str) -> tuple[str | None, str | None, int, int]:
    """
    回傳 (thumb_b64, preview_b64, orig_w, orig_h)。
    thumb: 150×150 object-fit cover (JPEG Q75)
    preview: 等比縮放至 max 640×640 (JPEG Q72)
    """
    try:
        from PIL import Image
        img = Image.open(file_path).convert("RGB")
        orig_w, orig_h = img.size

        # ── Thumbnail (150×150 center-crop) ───────────────────────────────
        ratio = max(150 / orig_w, 150 / orig_h)
        resized = img.resize(
            (max(150, int(orig_w * ratio)), max(150, int(orig_h * ratio))),
            Image.LANCZOS,
        )
        left = (resized.width - 150) // 2
        top  = (resized.height - 150) // 2
        thumb = resized.crop((left, top, left + 150, top + 150))
        buf = io.BytesIO()
        thumb.save(buf, format="JPEG", quality=75)
        thumb_b64 = base64.b64encode(buf.getvalue()).decode()

        # ── Preview (max 640×640, maintain aspect) ────────────────────────
        preview = img.copy()
        preview.thumbnail((640, 640), Image.LANCZOS)
        buf2 = io.BytesIO()
        preview.save(buf2, format="JPEG", quality=72)
        preview_b64 = base64.b64encode(buf2.getvalue()).decode()

        return thumb_b64, preview_b64, orig_w, orig_h
    except Exception:
        return None, None, 0, 0


# ─── CSV 匯出 ────────────────────────────────────────────────────────────────

def _build_csv(items: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["#", "item_id", "filename", "width", "height", "file_path", "file_hash"])
    for i, it in enumerate(items, 1):
        fp = it.get("file_path", "")
        w.writerow([
            i,
            it.get("item_id", ""),
            Path(fp).name if fp else "",
            it.get("width") or "",
            it.get("height") or "",
            fp,
            it.get("file_hash", ""),
        ])
    return buf.getvalue().encode("utf-8-sig")   # utf-8-sig → Excel 開啟不亂碼


# ─── HTML Table ──────────────────────────────────────────────────────────────

_CSS = """
<style>
  body { margin:0; font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         font-size:13px; color:#222; }
  table { border-collapse:collapse; width:100%; table-layout:fixed; }
  colgroup col.col-thumb { width:170px; }
  colgroup col.col-name  { width:220px; }
  colgroup col.col-dim   { width:110px; }
  colgroup col.col-path  { }
  thead th { background:#f0f2f6; padding:8px 10px; text-align:left;
              font-weight:600; font-size:12px; color:#555;
              border-bottom:2px solid #d0d3db; position:sticky; top:0; z-index:2; }
  tbody tr { border-bottom:1px solid #e8eaf0; }
  tbody tr:hover { background:#f7f8fc; }
  td { padding:8px 10px; vertical-align:middle; word-break:break-all; }
  td.col-thumb { padding:6px 10px; }
  .thumb-img { width:150px; height:150px; object-fit:cover; border-radius:6px;
               cursor:zoom-in; display:block;
               border:1px solid #dde; transition:box-shadow .15s; }
  .thumb-img:hover { box-shadow:0 0 0 3px #4e8cff66; }
  .fname { font-weight:500; color:#111; }
  .dim   { color:#666; font-size:12px; white-space:nowrap; }
  .fpath { color:#999; font-size:11px; }
  .no-img { width:150px; height:150px; background:#eee; border-radius:6px;
            display:flex; align-items:center; justify-content:center;
            color:#aaa; font-size:11px; text-align:center; line-height:1.4; }

  /* Hover popup */
  #cim-popup {
    display:none; position:fixed; z-index:99999;
    background:#fff; border:1.5px solid #bbb; border-radius:10px;
    padding:10px; box-shadow:0 6px 24px rgba(0,0,0,.28);
    pointer-events:none; max-width:660px;
  }
  #cim-popup img { max-width:640px; max-height:640px;
                   display:block; border-radius:4px; }
  #cim-popup .popup-dim { margin-top:6px; font-size:11px; color:#777;
                          text-align:center; }
</style>
"""

_JS = """
<div id="cim-popup">
  <img id="cim-popup-img" src="" alt="">
  <div class="popup-dim" id="cim-popup-dim"></div>
</div>
<script>
(function(){
  var popup  = document.getElementById('cim-popup');
  var pImg   = document.getElementById('cim-popup-img');
  var pDim   = document.getElementById('cim-popup-dim');

  function show(e) {
    var src = e.currentTarget.getAttribute('data-preview');
    var dim = e.currentTarget.getAttribute('data-dim');
    if (!src) return;
    pImg.src = src;
    pDim.textContent = dim || '';
    popup.style.display = 'block';
    move(e);
  }
  function move(e) {
    var x = e.clientX + 20, y = e.clientY - 20;
    var pw = popup.offsetWidth  || 660;
    var ph = popup.offsetHeight || 400;
    if (x + pw > window.innerWidth)  x = e.clientX - pw - 10;
    if (y + ph > window.innerHeight) y = window.innerHeight - ph - 10;
    if (y < 0) y = 4;
    popup.style.left = x + 'px';
    popup.style.top  = y + 'px';
  }
  function hide() { popup.style.display = 'none'; pImg.src = ''; }

  document.querySelectorAll('.thumb-img[data-preview]').forEach(function(el){
    el.addEventListener('mouseenter', show);
    el.addEventListener('mousemove',  move);
    el.addEventListener('mouseleave', hide);
  });
})();
</script>
"""


def _render_html_table(items: list[dict]) -> None:
    rows_html = []
    for idx, it in enumerate(items):
        fp = it.get("file_path", "")
        fname = Path(fp).name if fp else "（無路徑）"
        w = it.get("width") or 0
        h = it.get("height") or 0
        dim_str = f"{w} × {h} px" if w and h else "—"

        thumb_b64, preview_b64, orig_w, orig_h = _encode_item(fp) if fp else (None, None, w, h)
        real_dim = f"{orig_w} × {orig_h} px" if orig_w else dim_str

        if thumb_b64:
            preview_attr = f'data-preview="data:image/jpeg;base64,{preview_b64}"' if preview_b64 else ""
            thumb_html = (
                f'<img class="thumb-img" src="data:image/jpeg;base64,{thumb_b64}" '
                f'alt="{fname}" {preview_attr} data-dim="{real_dim}">'
            )
        else:
            thumb_html = f'<div class="no-img">⚠️<br>{fname[:20]}</div>'

        # 路徑：顯示最後兩層
        parts = Path(fp).parts if fp else []
        short_path = str(Path(*parts[-2:])) if len(parts) >= 2 else fp

        rows_html.append(
            f"<tr>"
            f"<td class='col-thumb'>{thumb_html}</td>"
            f"<td><span class='fname'>{fname}</span></td>"
            f"<td><span class='dim'>{real_dim}</span></td>"
            f"<td><span class='fpath' title='{fp}'>{short_path}</span></td>"
            f"</tr>"
        )

    table_html = (
        _CSS
        + "<table>"
        + "<colgroup>"
        + "<col class='col-thumb'><col class='col-name'>"
        + "<col class='col-dim'><col class='col-path'>"
        + "</colgroup>"
        + "<thead><tr>"
        + "<th>縮圖</th><th>檔名</th><th>尺寸</th><th>路徑</th>"
        + "</tr></thead>"
        + "<tbody>" + "".join(rows_html) + "</tbody>"
        + "</table>"
        + _JS
    )

    row_h = 166        # px per data row
    header_h = 40
    padding = 32
    iframe_h = header_h + len(items) * row_h + padding
    components.html(table_html, height=iframe_h, scrolling=False)


# ─── 主入口 ──────────────────────────────────────────────────────────────────

def render_output(result: dict) -> None:
    mode = result.get("mode", "idle")

    # ── idle ──────────────────────────────────────────────────────────────────
    if mode == "idle":
        st.info(
            "**使用方式：**\n\n"
            "1. 在左側 **Input** 頁面選擇資料來源類型（資料夾 / 資料庫 / API）\n"
            "2. 填寫對應設定並輸入 Manifest 名稱\n"
            "3. 點選「▶ 執行」\n"
            "4. 建立完成後，此頁面將顯示完整影像資料表"
        )
        return

    # ── error ─────────────────────────────────────────────────────────────────
    if mode == "error":
        st.error(f"❌ 建立 Manifest 失敗：{result.get('error', '未知錯誤')}")
        return

    # ── ready ─────────────────────────────────────────────────────────────────
    manifest_id   = result.get("manifest_id", "")
    manifest_name = result.get("manifest_name", "")
    source_type   = result.get("source_type", "")
    total_count   = result.get("total_count", 0)

    # 從 DB 讀取完整 items（result["items"] 只有前 20 筆）
    try:
        db_path = _cfg.get_manifest_db_path()
        all_items = _mdb.get_manifest_items(db_path, manifest_id)
    except Exception:
        all_items = result.get("items", [])

    # ── skip_preview：第一次顯示時自動跳到 Annotation Session ────────────────
    if result.get("skip_preview", False):
        _switched_key = f"m010_auto_switched_{manifest_id}"
        if not st.session_state.get(_switched_key):
            st.session_state[_switched_key] = True
            _post_message("SWITCH_TAB", {"plugin_id": "module_012", "tab": "input"})

    # ── Export 按鈕（最上方） ─────────────────────────────────────────────────
    csv_bytes = _build_csv(all_items)
    st.download_button(
        label=f"📤 Export CSV（{len(all_items)} 筆）",
        data=csv_bytes,
        file_name=f"{manifest_name}.csv",
        mime="text/csv",
        type="primary",
        use_container_width=False,
    )

    # ── Manifest 摘要 ─────────────────────────────────────────────────────────
    st.success(f"✅ **{manifest_name}**")
    st.caption(f"Manifest ID：`{manifest_id}`")
    c1, c2 = st.columns(2)
    c1.metric("總圖片數", f"{total_count:,}")
    c2.metric("來源類型", _SOURCE_LABEL.get(source_type, source_type))

    st.divider()

    # ── 資料表 ────────────────────────────────────────────────────────────────
    if not all_items:
        st.info("此 Manifest 沒有圖片項目。")
        return

    st.markdown(f"**影像資料表** — 共 {len(all_items):,} 筆")

    with st.spinner("載入縮圖中…"):
        _render_html_table(all_items)

    # ── 歷史 Manifest 清單 ────────────────────────────────────────────────────
    st.divider()
    with st.expander("📋 所有 Manifest 歷史記錄", expanded=False):
        try:
            import pandas as pd
            manifests = _mdb.list_manifests(db_path)
            if manifests:
                df = pd.DataFrame(manifests)[
                    ["manifest_id", "name", "source_type", "item_count", "status", "created_at"]
                ]
                df.columns = ["Manifest ID", "名稱", "來源", "圖片數", "狀態", "建立時間"]
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("尚未建立任何 Manifest。")
        except Exception as e:
            st.warning(f"無法載入 Manifest 清單：{e}")
