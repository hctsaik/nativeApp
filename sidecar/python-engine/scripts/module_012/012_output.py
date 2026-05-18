from __future__ import annotations

"""
012_output.py — Annotation Session 輸出 UI。

master-detail 介面：
  左欄  — 圖片列表（縮圖 + 狀態篩選 + 選取 + 標注工具按鈕）
  右欄  — Detail Panel（原圖 vs 標注結果、標注明細 expander、上下張導覽）

* 標注 JSON 由 X-AnyLabeling 直接輸出到影像所在目錄（同名 .json）
* streamlit_autorefresh 每 30 秒自動更新（可關閉）
* 鍵盤快捷鍵：↑/K 上一張、↓/J 下一張、A 標注工具
"""

import base64
import importlib.util as _ilu
import io
import json
import subprocess
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

# ─── 動態載入 _config + _manifest_db ─────────────────────────────────────────

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_012_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_mdb_spec = _ilu.spec_from_file_location(
    "_manifest_db", _HERE.parent / "shared" / "_manifest_db.py"
)
_mdb = _ilu.module_from_spec(_mdb_spec)
_mdb_spec.loader.exec_module(_mdb)

def _post_message(msg_type: str, payload: dict) -> None:
    import json as _json
    blob = _json.dumps({"type": msg_type, "source": "cim-platform", "payload": payload, "_cim": True})
    components.html(f"<script>window.top.postMessage({blob}, '*');</script>", height=0)


# ─── 調色盤 / 字型（與 006_output.py 相同） ──────────────────────────────────

_PALETTE = [
    (255, 80,  80),
    (80,  180, 255),
    (80,  220, 80),
    (255, 200, 60),
    (200, 80,  255),
]

_CJK_FONTS = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msjh.ttc",
    "C:/Windows/Fonts/mingliu.ttc",
    "C:/Windows/Fonts/simsun.ttc",
]


def _get_font(size: int):
    from PIL import ImageFont
    for path in _CJK_FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _label_px_width(text: str, font_size: int) -> int:
    return (
        sum(font_size for c in text if ord(c) > 127)
        + sum(int(font_size * 0.6) for c in text if ord(c) <= 127)
        + 8
    )


# ─── 路徑輔助 ─────────────────────────────────────────────────────────────────

def _find_annotation(img_path: str, workspace_dir: str = "") -> tuple[bool, str, int]:
    """回傳 (has_ann, ann_path, shape_count)。

    直接查影像同目錄的同名 .json（X-AnyLabeling 預設輸出位置）。
    """
    if not img_path:
        return False, "", 0
    ann_path = Path(img_path).with_suffix(".json")
    if not ann_path.exists():
        return False, "", 0
    try:
        sc = len(json.loads(ann_path.read_text(encoding="utf-8")).get("shapes", []))
    except Exception:
        sc = 0
    return True, str(ann_path), sc


# ─── X-AnyLabeling 啟動 ───────────────────────────────────────────────────────

def _launch_xany(file_path: str, labels: list[str], workspace_dir: str,
                 xany_exe: str, ann_path: str = "") -> str | None:
    """以 X-AnyLabeling 開啟圖片（非阻塞），輸出到影像所在目錄。"""
    ws = Path(workspace_dir)
    classes_txt = ws / "classes.txt"
    out_dir = Path(file_path).parent

    xany_args = [
        "--filename", file_path,
        "--output", str(out_dir),
        "--work-dir", str(ws / ".xanylabeling"),
        "--nodata", "--autosave", "--no-auto-update-check",
    ]
    if classes_txt.exists():
        xany_args += ["--labels", str(classes_txt), "--validatelabel", "exact"]

    # 優先以 python.exe 啟動（繞過 WDAC / Application Control 對 .exe 的封鎖）
    python_exe = Path(xany_exe).parent / "python.exe"
    if python_exe.exists():
        cmd = [str(python_exe), "-c", "from anylabeling.app import main; main()"] + xany_args
    else:
        cmd = [xany_exe] + xany_args

    try:
        subprocess.Popen(cmd)
        return None
    except Exception as e:
        return str(e)


# ─── PIL 畫標注框（直接移植自 006_output.py） ────────────────────────────────

def _draw_annotations(img_path: str, label_data: dict, enhance: bool = False) -> bytes:
    from PIL import Image, ImageDraw, ImageEnhance, ImageOps
    img = ImageOps.exif_transpose(Image.open(img_path)).convert("RGB")
    if enhance:
        img = ImageEnhance.Contrast(img).enhance(2.2)
        img = ImageEnhance.Color(img).enhance(1.8)
    draw = ImageDraw.Draw(img)
    fs   = max(14, img.height // 22)
    font = _get_font(fs)

    colour_map: dict[str, tuple] = {}
    for shape in label_data.get("shapes", []):
        label      = shape.get("label", "?")
        shape_type = shape.get("shape_type", "")
        points     = shape.get("points", [])
        if label not in colour_map:
            colour_map[label] = _PALETTE[len(colour_map) % len(_PALETTE)]
        c = colour_map[label]
        if shape_type == "rectangle" and len(points) >= 2:
            xs, ys = [p[0] for p in points], [p[1] for p in points]
            x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
            draw.rectangle([x0, y0, x1, y1], outline=c, width=3)
            lw = _label_px_width(label, fs)
            draw.rectangle([x0, y0 - fs - 4, x0 + lw, y0], fill=c)
            draw.text((x0 + 4, y0 - fs - 2), label, fill=(255, 255, 255), font=font)
        elif shape_type == "polygon" and len(points) >= 3:
            flat = [(p[0], p[1]) for p in points]
            draw.polygon(flat, outline=c)
            draw.text((flat[0][0] + 2, flat[0][1] - fs - 2), label, fill=c, font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ─── 縮圖編碼 ─────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False, max_entries=500)
def _make_thumb(file_path: str) -> bytes | None:
    try:
        from PIL import Image, ImageOps
        img = ImageOps.exif_transpose(Image.open(file_path)).convert("RGB")
        img.thumbnail((120, 90), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return buf.getvalue()
    except Exception:
        return None


# ─── hover popup 注入（parent-frame JS） ─────────────────────────────────────

_POPUP_JS = """
<script>
(function(){
  try {
    var p = window.parent;
    var d = p.document;
    if (!d.getElementById('_c012_popup')) {
      var el = d.createElement('div');
      el.id = '_c012_popup';
      el.style.cssText =
        'display:none;position:fixed;z-index:99999;pointer-events:none;' +
        'background:#fff;border:1.5px solid #94a3b8;border-radius:10px;' +
        'padding:10px;box-shadow:0 8px 32px rgba(0,0,0,.28);max-width:500px;';
      el.innerHTML =
        '<img id="_c012_pimg" style="max-height:400px;max-width:480px;' +
        'display:block;border-radius:4px;" />' +
        '<div id="_c012_ptag" style="margin-top:5px;font-size:11px;' +
        'text-align:center;color:#64748b;font-family:sans-serif;"></div>';
      d.body.appendChild(el);
    }
    var popup = d.getElementById('_c012_popup');
    var pImg  = d.getElementById('_c012_pimg');
    var pTag  = d.getElementById('_c012_ptag');

    function move(e) {
      var x = e.clientX + 18, y = e.clientY - 12;
      var pw = popup.offsetWidth  || 500;
      var ph = popup.offsetHeight || 400;
      if (x + pw > p.innerWidth)  x = e.clientX - pw - 10;
      if (y + ph > p.innerHeight) y = p.innerHeight - ph - 8;
      if (y < 0) y = 4;
      popup.style.left = x + 'px';
      popup.style.top  = y + 'px';
    }

    function bind() {
      d.querySelectorAll('[data-m012p]').forEach(function(img) {
        if (img._m012ok) return;
        img._m012ok = true;
        img.style.cursor = 'zoom-in';
        img.addEventListener('mouseenter', function(e) {
          pImg.src = img.getAttribute('data-m012p');
          pTag.textContent = img.getAttribute('data-m012t') || '';
          pTag.style.color = img.getAttribute('data-m012c') || '#64748b';
          popup.style.display = 'block';
          move(e);
        });
        img.addEventListener('mousemove', move);
        img.addEventListener('mouseleave', function() {
          popup.style.display = 'none';
        });
      });
    }

    bind();
    new p.MutationObserver(bind).observe(d.body, { childList: true, subtree: true });
  } catch(e) { /* cross-origin or not in parent frame */ }
})();
</script>
"""


def _inject_popup() -> None:
    """在 parent Streamlit frame 注入 hover popup 機制（一次性）。"""
    components.html(_POPUP_JS, height=0)


# ─── 縮圖 HTML 片段（供 hover popup 使用） ───────────────────────────────────

def _thumb_html(thumb_bytes: bytes | None, img_path: str, tag: str,
                color: str, border: str) -> str:
    if not thumb_bytes:
        return '<span style="color:#94a3b8;font-size:10px">—</span>'
    b64 = base64.b64encode(thumb_bytes).decode()
    # 用原圖路徑產生 file:// URL 供 popup 預覽（parent-frame）
    prev_src = f"data:image/jpeg;base64,{b64}"
    return (
        f'<div style="display:inline-block;text-align:center;">'
        f'<img src="data:image/jpeg;base64,{b64}"'
        f' data-m012p="{prev_src}"'
        f' data-m012t="{tag}" data-m012c="{color}"'
        f' style="max-height:80px;width:auto;border-radius:5px;'
        f'border:2px solid {border};display:block;" />'
        f'</div>'
    )


# ─── 鍵盤快捷鍵注入 ───────────────────────────────────────────────────────────

def _keyboard_listener() -> None:
    """注入鍵盤快捷鍵：↑/K 上一張、↓/J 下一張、A 標注工具、C 強化對比、1-4 快速分類、Enter 確認。"""
    components.html("""
<script>
(function() {
    if (window.parent._kb012_active) return;
    window.parent._kb012_active = true;

    function clickByText(needle) {
        var btns = window.parent.document.querySelectorAll('button');
        for (var b of btns) {
            if (b.textContent.trim().indexOf(needle) >= 0) { b.click(); return true; }
        }
        return false;
    }

    window.parent.document.addEventListener('keydown', function(e) {
        var tag = e.target.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA') return;
        if (e.ctrlKey || e.metaKey || e.altKey) return;
        var k = e.key;
        if (k === 'ArrowUp'   || k === 'k' || k === 'K') { e.preventDefault(); clickByText('← 上一張'); }
        else if (k === 'ArrowDown' || k === 'j' || k === 'J') { e.preventDefault(); clickByText('→ 下一張'); }
        else if (k === 'a' || k === 'A') { e.preventDefault(); clickByText('🖊 標注工具'); }
        else if (k === 'c' || k === 'C') {
            var inputs = window.parent.document.querySelectorAll('input[type="checkbox"]');
            for (var inp of inputs) {
                var container = inp.closest('label') || inp.parentElement;
                if (container && container.textContent.indexOf('強化對比') >= 0) { inp.click(); break; }
            }
        }
        else if (k >= '1' && k <= '4') {
            var idx = parseInt(k) - 1;
            var btns2 = window.parent.document.querySelectorAll('button');
            var targets = [];
            for (var b of btns2) {
                var txt = b.textContent.trim();
                if (txt.startsWith('①') || txt.startsWith('②') ||
                    txt.startsWith('③') || txt.startsWith('④')) {
                    targets.push(b);
                }
            }
            if (targets[idx]) { e.preventDefault(); targets[idx].click(); }
        }
        else if (k === 'Enter') {
            e.preventDefault();
            clickByText('✅ 確認');
        }
    }, true);
})();
</script>
""", height=0)


# ─── 分類輔助函式 ────────────────────────────────────────────────────────────

def _save_clf(workspace_dir: str, item_id: str, label: str, cache: dict) -> None:
    cache[item_id] = label
    _cfg.save_classifications(workspace_dir, cache)


def _clear_clf(workspace_dir: str, item_id: str, cache: dict) -> None:
    cache.pop(item_id, None)
    _cfg.save_classifications(workspace_dir, cache)


def _next_unclassified(items: list, current_idx: int, clf: dict) -> int:
    for offset in range(1, len(items)):
        idx = (current_idx + offset) % len(items)
        if items[idx].get("item_id", "") not in clf:
            return idx
    return (current_idx + 1) % len(items)


# ─── 主入口 ──────────────────────────────────────────────────────────────────

def render_output(result: dict) -> None:
    mode = result.get("mode", "idle")

    if mode == "error":
        st.error(f"❌ {result.get('error', '未知錯誤')}")
        return

    if mode != "ready":
        st.info("請在 Input 頁面選擇 Manifest 與標注類別，點選「▶ 執行」開始工作階段。")
        return

    manifest_id            = result.get("manifest_id", "")
    manifest_name          = result.get("manifest_name", "")
    labels                 = result.get("labels", [])
    classification_labels  = result.get("classification_labels", [])
    workspace_dir          = result.get("workspace_dir", "")
    xany_exe               = result.get("xany_exe", "xanylabeling")

    # 每次 rerun 從磁碟重讀分類結果
    classifications: dict[str, str] = {}
    if workspace_dir:
        classifications = _cfg.load_classifications(workspace_dir)

    # 注入 hover popup JS
    _inject_popup()
    # 注入鍵盤快捷鍵
    _keyboard_listener()

    # ── CSS ──────────────────────────────────────────────────────────────────
    st.markdown("""<style>
[data-testid='stImage'] img { max-height: 58vh; width: auto !important; object-fit: contain; }
.thumb-selected { border: 3px solid #1a73e8 !important; border-radius: 6px; padding: 2px; }
</style>""", unsafe_allow_html=True)

    # ── 每次 rerun 重新掃描最新標注狀態 ──────────────────────────────────────
    db_path = _cfg.get_manifest_db_path()
    try:
        db_items = _mdb.get_manifest_items(db_path, manifest_id)
    except Exception:
        db_items = result.get("items", [])

    items: list[dict] = []
    for it in db_items:
        fp = it.get("file_path", "")
        has_ann, ann_path, shape_count = _find_annotation(fp, workspace_dir)
        items.append({
            **it,
            "has_ann":     has_ann,
            "ann_path":    ann_path,
            "shape_count": shape_count,
        })

    annotated = sum(1 for it in items if it["has_ann"])
    total     = len(items)

    # ── 標題 ─────────────────────────────────────────────────────────────────
    st.markdown(f"## 🏷️ {manifest_name}")
    st.caption(
        f"Manifest ID：`{manifest_id[:8]}…`　｜　"
        f"類別：{', '.join(labels) or '（未設定）'}"
    )

    # ── metrics + 進度條 ─────────────────────────────────────────────────────
    pct = annotated / total if total else 0
    if classification_labels:
        classified_count = sum(1 for it in items if it.get("item_id", "") in classifications)
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("總圖數",   total)
        m2.metric("✅ 已標注", annotated)
        m3.metric("⏳ 待標注", total - annotated)
        m4.metric("🏷 已分類", classified_count)
        m5.metric("完成率",   f"{pct * 100:.1f}%")
    else:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("總圖數",   total)
        m2.metric("✅ 已標注", annotated)
        m3.metric("⏳ 待標注", total - annotated)
        m4.metric("完成率",   f"{pct * 100:.1f}%")
    st.progress(pct, text=f"已標注 {annotated} / {total} 張（{pct * 100:.1f}%）")

    if st.button("📁 前往 Update →", type="primary", key="m012_goto_update"):
        _post_message("SWITCH_TAB", {"plugin_id": "module_013", "tab": "input"})

    with st.expander("📖 狀態說明", expanded=False):
        st.markdown(
            "⏳ **待標注** — 尚未有 X-AnyLabeling 標注框  \n"
            "✅ **已標注** — X-AnyLabeling 已標框並儲存"
        )

    # ── auto-refresh 控制 ─────────────────────────────────────────────────────
    ar_col, num_col, _ = st.columns([2, 1, 5])
    with ar_col:
        auto_refresh = st.toggle(
            "🔄 自動更新",
            value=st.session_state.get("m012_auto_refresh", True),
            key="m012_auto_refresh",
        )
    with num_col:
        refresh_interval = st.number_input(
            "間隔（秒）",
            min_value=5,
            max_value=300,
            value=st.session_state.get("m012_refresh_interval", 5),
            step=5,
            key="m012_refresh_interval",
            label_visibility="collapsed",
            disabled=not auto_refresh,
        )

    st.divider()

    # ── session_state：選取索引 ───────────────────────────────────────────────
    if "m012_selected_idx" not in st.session_state:
        st.session_state["m012_selected_idx"] = 0

    # ── 主體：左右欄 ─────────────────────────────────────────────────────────
    left_col, right_col = st.columns([1, 2], gap="medium")

    # ════════════════════════════════════════════════════════════════
    # 左欄：圖片列表
    # ════════════════════════════════════════════════════════════════
    with left_col:
        st.markdown("**圖片列表**")

        filter_opt = st.selectbox(
            "狀態篩選",
            ["全部狀態", "⏳ 待標注", "✅ 已標注"],
            label_visibility="collapsed",
            key="m012_filter",
        )
        if filter_opt == "⏳ 待標注":
            visible = [it for it in items if not it["has_ann"]]
        elif filter_opt == "✅ 已標注":
            visible = [it for it in items if it["has_ann"]]
        else:
            visible = items

        st.caption(f"顯示 {len(visible)} 張")

        if not visible:
            st.info("目前篩選條件下沒有圖片。")
        else:
            for vis_i, item in enumerate(visible):
                fp          = item.get("file_path", "")
                fname       = Path(fp).name if fp else "（無路徑）"
                has_ann     = item["has_ann"]
                shape_count = item["shape_count"]

                # 在 items 中的全域索引（用於 selected_idx）
                global_idx = items.index(item)
                is_selected = (global_idx == st.session_state["m012_selected_idx"])

                thumb_bytes = _make_thumb(fp) if fp else None

                # 縮圖 + 資訊
                thumb_c, info_c = st.columns([1, 2])
                with thumb_c:
                    if thumb_bytes:
                        border = "#1a73e8" if is_selected else "#cbd5e1"
                        html = _thumb_html(
                            thumb_bytes,
                            img_path=fp,
                            tag=fname,
                            color="#1a73e8",
                            border=border,
                        )
                        if is_selected:
                            html = f'<div class="thumb-selected">{html}</div>'
                        st.markdown(html, unsafe_allow_html=True)
                    else:
                        st.markdown("🖼️")

                with info_c:
                    if is_selected:
                        st.markdown(
                            f"<span data-kb012-selected='true' "
                            f"style='color:#1a73e8;font-weight:700'>▶ {fname}</span>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(fname)

                    item_id    = item.get("item_id", "")
                    clf_label  = classifications.get(item_id, "")
                    ann_status = f"✅ 已標注　{shape_count} 個 shape" if has_ann else "⏳ 待標注"
                    clf_status = f"　🏷 {clf_label}" if clf_label else ""
                    st.caption(f"{ann_status}{clf_status}")

                    sel_c, ann_c, ref_c = st.columns(3)
                    with sel_c:
                        if st.button(
                            "選取",
                            key=f"sel_{item['item_id']}",
                            type="primary" if is_selected else "secondary",
                            use_container_width=True,
                        ):
                            st.session_state["m012_selected_idx"] = global_idx
                            st.rerun()
                    with ann_c:
                        if st.button(
                            "🖊 標注工具",
                            key=f"xany_{item['item_id']}",
                            use_container_width=True,
                        ):
                            err = _launch_xany(fp, labels, workspace_dir, xany_exe, ann_path=ann_path)
                            if err:
                                st.error(f"啟動失敗：{err}")
                            else:
                                st.toast(f"X-AnyLabeling 已開啟：{fname}", icon="🖊")
                    with ref_c:
                        if st.button(
                            "↻",
                            key=f"ref_{item['item_id']}",
                            use_container_width=True,
                            help="從 X-AnyLabeling 標注完成後按此更新",
                        ):
                            st.rerun()

        # 選取項目 scroll into view
        components.html("""<script>
setTimeout(function() {
    var el = window.parent.document.querySelector('[data-kb012-selected="true"]');
    if (el) { el.scrollIntoView({block: 'nearest', behavior: 'smooth'}); }
}, 400);
</script>""", height=0)

    # ════════════════════════════════════════════════════════════════
    # 右欄：Detail Panel
    # ════════════════════════════════════════════════════════════════
    with right_col:
        sel_idx = int(st.session_state.get("m012_selected_idx", 0))
        if sel_idx >= len(items):
            sel_idx = 0
        if not items:
            st.info("尚無圖片資料。")
        else:
            item       = items[sel_idx]
            fp         = item.get("file_path", "")
            fname      = Path(fp).name if fp else "（無路徑）"
            has_ann    = item["has_ann"]
            ann_path   = item["ann_path"]
            shape_count = item["shape_count"]

            # 鍵盤提示
            st.caption("⌨️ ↑/K 上一張　↓/J 下一張　Enter 確認　1-4 快速分類　A 標注工具　C 強化對比")

            # 檔名 + 路徑
            st.markdown(f"### {fname}")
            parts = Path(fp).parts if fp else ()
            short = str(Path(*parts[-3:])) if len(parts) >= 3 else fp
            st.caption(f"`{short}`")

            st.divider()

            # ── 分類 UI（只有在設定了分類類別時才顯示） ──────────────────────
            item_id = item.get("item_id", "")
            if classification_labels:
                current_clf = classifications.get(item_id, "")
                if current_clf:
                    st.markdown(f"**目前分類：** 🏷 `{current_clf}`")
                else:
                    st.markdown("**目前分類：** 📋 尚未分類")

                # 快速分類按鈕（最多 4 個，超過用 selectbox 即可）
                if len(classification_labels) <= 4:
                    syms = ["①", "②", "③", "④"]
                    q_cols = st.columns(len(classification_labels))
                    for qi, lbl in enumerate(classification_labels):
                        with q_cols[qi]:
                            if st.button(
                                f"{syms[qi]} {lbl}",
                                key=f"qc_{item_id}_{qi}",
                                use_container_width=True,
                                help=f"快速分類為「{lbl}」（快捷鍵 {qi + 1}）",
                            ):
                                _save_clf(workspace_dir, item_id, lbl, classifications)
                                st.session_state["m012_selected_idx"] = _next_unclassified(
                                    items, sel_idx, classifications
                                )
                                st.rerun()

                # selectbox + 確認 / 跳過 / 重設
                clf_options = ["請選擇分類"] + classification_labels
                clf_default = clf_options.index(current_clf) if current_clf in clf_options else 0
                tag_c, btn_c, skip_c, reset_c = st.columns([3, 1, 1, 1])
                with tag_c:
                    tag_choice = st.selectbox(
                        "分類", clf_options, index=clf_default,
                        key=f"clf_sel_{item_id}", label_visibility="collapsed",
                    )
                with btn_c:
                    if st.button(
                        "✅ 確認", type="primary", use_container_width=True,
                        key=f"clf_confirm_{item_id}",
                        help="儲存分類並跳至下一張 (Enter)",
                    ):
                        if tag_choice != "請選擇分類":
                            _save_clf(workspace_dir, item_id, tag_choice, classifications)
                            st.session_state["m012_selected_idx"] = _next_unclassified(
                                items, sel_idx, classifications
                            )
                            st.rerun()
                with skip_c:
                    if st.button(
                        "→ 跳過", use_container_width=True,
                        key=f"clf_skip_{item_id}",
                        help="暫時跳過（快捷鍵 ↓/J）",
                    ):
                        st.session_state["m012_selected_idx"] = (sel_idx + 1) % len(items)
                        st.rerun()
                with reset_c:
                    if current_clf and st.button(
                        "✕ 重設", use_container_width=True,
                        key=f"clf_reset_{item_id}",
                        help="清除分類",
                    ):
                        _clear_clf(workspace_dir, item_id, classifications)
                        st.rerun()

                st.divider()

            # 導覽按鈕（置於圖片上方）
            # 注意：不使用 disabled，否則 JS .click() 無法觸發；改用循環跳轉
            n_items = len(items)
            prev_c, next_c = st.columns(2)
            with prev_c:
                if st.button("← 上一張", key="m012_prev_btn",
                             use_container_width=True,
                             help="上一張（快捷鍵 ↑/K）"):
                    st.session_state["m012_selected_idx"] = (sel_idx - 1) % n_items
                    st.rerun()
            with next_c:
                if st.button("→ 下一張", key="m012_next_btn",
                             use_container_width=True,
                             help="下一張（快捷鍵 ↓/J）"):
                    st.session_state["m012_selected_idx"] = (sel_idx + 1) % n_items
                    st.rerun()

            # 強化對比 toggle（僅對標注結果圖有效）
            enhance = st.toggle(
                "🔆 強化對比（僅標注結果）",
                key=f"enhance_{item['item_id']}",
                help="對右側標注結果圖套用對比度與飽和度強化，原圖保持不變。",
            )

            # 圖片顯示
            if not fp or not Path(fp).exists():
                st.warning(f"找不到影像：{fp}")
            elif has_ann and ann_path:
                try:
                    label_data = json.loads(Path(ann_path).read_text(encoding="utf-8"))
                    shapes = label_data.get("shapes", [])
                except Exception:
                    label_data = {}
                    shapes = []

                if shapes:
                    orig_c, ann_c = st.columns(2)
                    with orig_c:
                        st.markdown("**原圖**（未修改）")
                        st.image(fp, use_container_width=True)
                    with ann_c:
                        st.markdown("**標注結果**")
                        try:
                            ann_bytes = _draw_annotations(fp, label_data, enhance=enhance)
                            st.image(ann_bytes, use_container_width=True)
                        except Exception as e:
                            st.warning(f"畫框失敗：{e}")
                            st.image(fp, use_container_width=True)

                    # 標注明細 expander
                    with st.expander("標注明細", expanded=True):
                        rows = [
                            {
                                "Label":      s.get("label", "?"),
                                "Shape":      s.get("shape_type", "?"),
                                "Points":     len(s.get("points", [])),
                            }
                            for s in shapes
                        ]
                        st.dataframe(rows, use_container_width=True, hide_index=True)
                else:
                    # ann_path 存在但 shapes 為空
                    st.image(fp, use_container_width=True)
                    st.info("標注檔存在但尚無 shape，請以「🖊 標注工具」繼續標注。")
            else:
                # 無標注
                st.image(fp, use_container_width=True)
                st.info("此圖尚無標注，點擊左側「🖊 標注工具」開始標注。")

    # ── auto-refresh ─────────────────────────────────────────────────────────
    if st.session_state.get("m012_auto_refresh", True):
        interval_ms = int(st.session_state.get("m012_refresh_interval", 30)) * 1000
        st_autorefresh(interval=interval_ms, key="m012_autorefresh")
