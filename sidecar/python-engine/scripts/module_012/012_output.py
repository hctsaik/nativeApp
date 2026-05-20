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
import os
import subprocess
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

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


# ─── 標注狀態快取（session_state + mtime 增量更新） ──────────────────────────

PAGE_SIZE = 50


def _scan_items(db_items: list[dict], workspace_dir: str) -> tuple[list[dict], dict[str, float]]:
    """Full scan — 首次載入或 manifest 換新時呼叫。"""
    items: list[dict] = []
    mtimes: dict[str, float] = {}
    for it in db_items:
        fp = it.get("file_path", "")
        has_ann, ann_path, shape_count = _find_annotation(fp, workspace_dir)
        items.append({**it, "has_ann": has_ann, "ann_path": ann_path, "shape_count": shape_count})
        if ann_path:
            try:
                mtimes[ann_path] = Path(ann_path).stat().st_mtime
            except Exception:
                mtimes[ann_path] = 0.0
    return items, mtimes


def _incremental_refresh(
    cached: list[dict], mtimes: dict[str, float], workspace_dir: str
) -> tuple[list[dict], dict[str, float]]:
    """每次 rerun 只做 stat() 比對，僅對變動的項目重讀 JSON。"""
    new_mtimes = dict(mtimes)
    for item in cached:
        fp = item.get("file_path", "")
        if not fp:
            continue
        ann_path = item.get("ann_path", "")
        if ann_path:
            try:
                mtime = Path(ann_path).stat().st_mtime
            except FileNotFoundError:
                mtime = -1.0
            except Exception:
                mtime = new_mtimes.get(ann_path, 0.0)
            if mtime != new_mtimes.get(ann_path, -999.0):
                has_ann, new_ap, sc = _find_annotation(fp, workspace_dir)
                item["has_ann"] = has_ann
                item["ann_path"] = new_ap
                item["shape_count"] = sc
                if ann_path != new_ap:
                    new_mtimes.pop(ann_path, None)
                if new_ap:
                    try:
                        new_mtimes[new_ap] = Path(new_ap).stat().st_mtime
                    except Exception:
                        new_mtimes[new_ap] = 0.0
        else:
            # 尚無標注：只做 exists()，不讀檔案內容
            candidate = Path(fp).with_suffix(".json")
            if candidate.exists():
                has_ann, new_ap, sc = _find_annotation(fp, workspace_dir)
                item["has_ann"] = has_ann
                item["ann_path"] = new_ap
                item["shape_count"] = sc
                if new_ap:
                    try:
                        new_mtimes[new_ap] = Path(new_ap).stat().st_mtime
                    except Exception:
                        new_mtimes[new_ap] = 0.0
    return cached, new_mtimes


def _get_items(manifest_id: str, workspace_dir: str, db_items: list[dict]) -> list[dict]:
    """session_state 快取入口：cache miss → full scan；hit → incremental refresh。"""
    cached = st.session_state.get("m012_items")
    if (
        st.session_state.get("m012_cache_mid") != manifest_id
        or cached is None
        or len(cached) != len(db_items)
    ):
        items, mtimes = _scan_items(db_items, workspace_dir)
        st.session_state["m012_items"]     = items
        st.session_state["m012_mtimes"]    = mtimes
        st.session_state["m012_cache_mid"] = manifest_id
        return items

    items, mtimes = _incremental_refresh(cached, st.session_state["m012_mtimes"], workspace_dir)
    st.session_state["m012_items"]  = items
    st.session_state["m012_mtimes"] = mtimes
    return items


# ─── X-AnyLabeling 啟動 ───────────────────────────────────────────────────────

def _find_venv_python_cmd(xany_exe: str) -> list[str]:
    """Return argv prefix [python, ...flags] for a WDAC-trusted Python matching the venv's ABI.

    Reads the Python version from pyvenv.cfg (e.g. 3.11 or 3.12), then tries:
      1. py.exe -3.X  (Windows Python Launcher — Microsoft-signed, always WDAC-trusted)
      2. Common python.org install paths for that version (PSF-signed)
      3. pyvenv.cfg home directory (uv-managed, may be WDAC-blocked)
      4. venv python.exe fallback
    """
    import shutil

    # Determine required version from pyvenv.cfg (e.g. "3.12" → ver="3.12", short="312")
    pyvenv_cfg = Path(xany_exe).parents[1] / "pyvenv.cfg"
    ver = ""
    if pyvenv_cfg.exists():
        for _line in pyvenv_cfg.read_text(encoding="utf-8").splitlines():
            if _line.startswith("version_info"):
                ver = ".".join(_line.split("=", 1)[1].strip().split(".")[:2])
                break

    # 1. py.exe launcher (Microsoft-signed, WDAC-trusted)
    if ver:
        py = shutil.which("py")
        if py:
            try:
                r = subprocess.run([py, f"-{ver}", "--version"], capture_output=True, timeout=5)
                if r.returncode == 0:
                    return [py, f"-{ver}"]
            except Exception:
                pass

    # 2. Common python.org install paths (PSF-signed)
    localappdata = os.environ.get("LOCALAPPDATA", "")
    short = ver.replace(".", "") if ver else ""
    for candidate in [
        Path(localappdata) / "Programs" / "Python" / f"Python{short}" / "python.exe",
        Path(localappdata) / "Python" / f"pythoncore-{ver}-64" / "python.exe",
        Path(f"C:\\Program Files\\Python{short}\\python.exe"),
        Path(f"C:\\Python{short}\\python.exe"),
    ]:
        if candidate.exists():
            return [str(candidate)]

    # 3. pyvenv.cfg home (uv-managed, may be WDAC-blocked — last resort before venv stub)
    if pyvenv_cfg.exists():
        for _line in pyvenv_cfg.read_text(encoding="utf-8").splitlines():
            if _line.startswith("home"):
                _cand = Path(_line.split("=", 1)[1].strip()) / "python.exe"
                if _cand.exists():
                    return [str(_cand)]

    return [str(Path(xany_exe).parent / "python.exe")]


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

    # WDAC 繞過策略：
    #   xanylabeling.exe 與 .venv-xanylabeling/Scripts/python.exe 均為 uv trampoline（未簽章），
    #   uv 自動下載的 CPython 3.12 同樣未簽章 — 三者都被 WDAC 封鎖。
    #   需使用 PSF-signed 的 Python 3.12（从 python.org 安裝）。
    #   優先序：py.exe -3.12 launcher（Microsoft-signed）→ 常見 PSF 安裝路徑 → pyvenv.cfg home → fallback
    venv_root = Path(xany_exe).parents[1]
    venv_sp = str(venv_root / "Lib" / "site-packages")
    launch_stmt = f"import sys; sys.path.insert(0, r'{venv_sp}'); from anylabeling.app import main; main()"
    python_cmd = _find_venv_python_cmd(xany_exe)
    cmd = python_cmd + ["-c", launch_stmt] + xany_args

    try:
        subprocess.Popen(cmd)
        return None
    except Exception as e:
        if "4551" in str(e) or "policy" in str(e).lower() or "blocked" in str(e).lower():
            return (
                f"{e}\n\n"
                "【解決方法】請安裝官方 Python 3.12：\n"
                "  https://www.python.org/downloads/release/python-3128/\n"
                "  安裝後重啟應用程式即可自動使用。"
            )
        return str(e)


def _show_img(fp: str, enhance: bool) -> None:
    """Display image in right panel; apply contrast enhancement when enhance=True."""
    if enhance:
        try:
            st.image(_draw_annotations(fp, {}, enhance=True), use_container_width=True)
            return
        except Exception:
            pass
    st.image(fp, use_container_width=True)


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


@st.cache_data(show_spinner=False, max_entries=500)
def _make_ann_thumb(file_path: str, ann_path: str) -> bytes | None:
    """標注結果縮圖（含框線），用於左欄列表。"""
    try:
        label_data = json.loads(Path(ann_path).read_text(encoding="utf-8"))
        ann_bytes = _draw_annotations(file_path, label_data, enhance=False)
        from PIL import Image
        img = Image.open(io.BytesIO(ann_bytes))
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
    """注入鍵盤快捷鍵 + 隱藏幽靈按鈕。

    快捷鍵對應：
      ↑/K  — 上一張      ↓/J — 下一張
      A    — 標注工具    C   — 強化對比
      1-9  — 快速分類（①②③…）
    """
    components.html("""
<script>
(function() {
    if (window.parent._kb012_active) return;
    window.parent._kb012_active = true;
    var d = window.parent.document;

    // 將幽靈按鈕縮成 1×1px 隱形（pointer-events:none 不影響 JS .click()）
    function hideGhosts() {
        d.querySelectorAll('button').forEach(function(b) {
            var txt = b.textContent.trim();
            if (txt === '← 上一張' || txt === '→ 下一張' ||
                /^[①②③④⑤⑥⑦⑧⑨]/.test(txt)) {
                b.style.cssText += ';position:fixed!important;opacity:0!important;' +
                    'pointer-events:none!important;width:1px!important;' +
                    'height:1px!important;overflow:hidden!important;padding:0!important;border:0!important;';
                var wrap = b.closest('[data-testid="stButton"]');
                if (wrap) wrap.style.cssText += ';position:fixed!important;opacity:0!important;' +
                    'pointer-events:none!important;width:1px!important;height:1px!important;overflow:hidden!important;';
            }
        });
    }
    hideGhosts();
    new MutationObserver(hideGhosts).observe(d.body, {childList: true, subtree: true});

    function clickByText(needle) {
        var btns = d.querySelectorAll('button');
        for (var b of btns) {
            if (b.textContent.trim().indexOf(needle) >= 0) { b.click(); return true; }
        }
        return false;
    }

    d.addEventListener('keydown', function(e) {
        var tag = e.target.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
        if (e.ctrlKey || e.metaKey || e.altKey) return;
        var k = e.key;
        if (k === 'ArrowUp' || k === 'k' || k === 'K') {
            e.preventDefault(); clickByText('← 上一張');
        } else if (k === 'ArrowDown' || k === 'j' || k === 'J') {
            e.preventDefault(); clickByText('→ 下一張');
        } else if (k === 'a' || k === 'A') {
            e.preventDefault(); clickByText('🖊 標注工具');
        } else if (k === 'c' || k === 'C') {
            var inputs = d.querySelectorAll('input[type="checkbox"]');
            for (var inp of inputs) {
                var cont = inp.closest('label') || inp.parentElement;
                if (cont && cont.textContent.indexOf('對比') >= 0) { inp.click(); break; }
            }
        } else if (k >= '1' && k <= '9') {
            var syms = ['①','②','③','④','⑤','⑥','⑦','⑧','⑨'];
            e.preventDefault(); clickByText(syms[parseInt(k) - 1]);
        }
    }, true);
})();
</script>
""", height=0)


# ─── 分類輔助函式 ────────────────────────────────────────────────────────────

def _save_clf(workspace_dir: str, item_id: str, label: str, cache: dict) -> None:
    if not workspace_dir:
        return
    cache[item_id] = label
    _cfg.save_classifications(workspace_dir, cache)


def _clear_clf(workspace_dir: str, item_id: str, cache: dict) -> None:
    if not workspace_dir:
        return
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

    # ── 標注狀態：session_state 快取 + mtime 增量更新 ─────────────────────────
    db_path = _cfg.get_manifest_db_path()
    try:
        db_items = _mdb.get_manifest_items(db_path, manifest_id)
    except Exception:
        db_items = result.get("items", [])

    items     = _get_items(manifest_id, workspace_dir, db_items)
    annotated = sum(1 for it in items if it["has_ann"])
    total     = len(items)

    # ── 標題 ─────────────────────────────────────────────────────────────────
    st.markdown(f"## 🏷️ {manifest_name}")

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

        # 篩選切換時重設頁碼
        if st.session_state.get("m012_prev_filter") != filter_opt:
            st.session_state["m012_page"]        = 0
            st.session_state["m012_prev_filter"] = filter_opt

        st.caption(f"顯示 {len(visible)} 張")

        # O(1) 全域索引表（item_id → items 中的位置）
        item_id_to_global = {it.get("item_id", ""): i for i, it in enumerate(items)}

        # Pagination 計算
        n_visible  = len(visible)
        n_pages    = max(1, (n_visible + PAGE_SIZE - 1) // PAGE_SIZE)
        page       = max(0, min(st.session_state.get("m012_page", 0), n_pages - 1))
        sel_idx    = st.session_state.get("m012_selected_idx", 0)

        # 選取項目所在頁自動跟隨（僅限鍵盤 ↑/↓ 導覽，避免覆蓋分頁按鈕的跳頁）
        if st.session_state.pop("m012_kbd_nav", False):
            for _vi, _it in enumerate(visible):
                if item_id_to_global.get(_it.get("item_id", "")) == sel_idx:
                    desired = _vi // PAGE_SIZE
                    if desired != page:
                        page = desired
                        st.session_state["m012_page"] = page
                    break

        page_start = page * PAGE_SIZE
        page_end   = min(page_start + PAGE_SIZE, n_visible)
        page_items = visible[page_start:page_end]

        if not visible:
            st.info("目前篩選條件下沒有圖片。")
        else:
            # ─ 分頁控制列（上方）────────────────────────────────────
            if n_pages > 1:
                pg_prev, pg_info, pg_next = st.columns([1, 3, 1])
                with pg_prev:
                    if st.button("◀", key="m012_pg_prev_top", disabled=(page == 0),
                                 use_container_width=True):
                        st.session_state["m012_page"] = page - 1
                with pg_info:
                    st.caption(f"第 {page + 1} / {n_pages} 頁（共 {n_visible} 張）")
                with pg_next:
                    if st.button("▶", key="m012_pg_next_top", disabled=(page == n_pages - 1),
                                 use_container_width=True):
                        st.session_state["m012_page"] = page + 1

            for vis_i, item in enumerate(page_items):
                fp          = item.get("file_path", "")
                fname       = Path(fp).name if fp else "（無路徑）"
                has_ann     = item["has_ann"]
                shape_count = item["shape_count"]

                global_idx  = item_id_to_global.get(item.get("item_id", ""), page_start + vis_i)
                is_selected = (global_idx == sel_idx)

                thumb_bytes = _make_thumb(fp) if fp else None
                ann_thumb_bytes = (
                    _make_ann_thumb(fp, item["ann_path"])
                    if has_ann and item["ann_path"] else None
                )

                # 原圖縮圖 | 標注縮圖 | 資訊
                thumb_c, ann_c, info_c = st.columns([1, 1, 2])
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

                with ann_c:
                    if ann_thumb_bytes:
                        ann_html = _thumb_html(
                            ann_thumb_bytes,
                            img_path=fp,
                            tag=f"{fname} (標注)",
                            color="#16a34a",
                            border="#16a34a",
                        )
                        st.markdown(ann_html, unsafe_allow_html=True)
                    elif has_ann:
                        st.markdown('<span style="color:#94a3b8;font-size:10px">無框</span>',
                                    unsafe_allow_html=True)

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

                    sel_c, ann_c = st.columns(2)
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
                            err = _launch_xany(fp, labels, workspace_dir, xany_exe, ann_path=item["ann_path"])
                            if err:
                                st.error(f"啟動失敗：{err}")
                            else:
                                st.toast(f"X-AnyLabeling 已開啟：{fname}", icon="🖊")

            # ─ 分頁控制列 ────────────────────────────────────────────
            if n_pages > 1:
                pg_prev, pg_info, pg_next = st.columns([1, 3, 1])
                with pg_prev:
                    if st.button("◀", key="m012_pg_prev", disabled=(page == 0),
                                 use_container_width=True):
                        st.session_state["m012_page"] = page - 1
                with pg_info:
                    st.caption(f"第 {page + 1} / {n_pages} 頁（共 {n_visible} 張）")
                with pg_next:
                    if st.button("▶", key="m012_pg_next", disabled=(page == n_pages - 1),
                                 use_container_width=True):
                        st.session_state["m012_page"] = page + 1

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

            # 檔名 + 路徑合併 + 強化對比（同一列）
            parts = Path(fp).parts if fp else ()
            short = str(Path(*parts[-3:])) if len(parts) >= 3 else fp
            fname_c, enhance_c = st.columns([4, 1])
            with fname_c:
                st.markdown(f"**{fname}**  \n`{short}`")
            with enhance_c:
                st.markdown("<div style='margin-top:8px'>", unsafe_allow_html=True)
                enhance = st.toggle(
                    "🔆 對比",
                    key=f"enhance_{item['item_id']}",
                    help="強化對比度與飽和度（僅影響標注結果顯示）",
                )
                st.markdown("</div>", unsafe_allow_html=True)

            st.divider()

            # ── 分類 UI（只有在設定了分類類別時才顯示） ──────────────────────
            item_id = item.get("item_id", "")
            n_items = len(items)

            # ── 幽靈導覽按鈕（鍵盤 ↑/K ↓/J 用，JS 會隱形化） ─────────────────
            if st.button("← 上一張", key="m012_prev_btn"):
                st.session_state["m012_selected_idx"] = (sel_idx - 1) % n_items
                st.session_state["m012_kbd_nav"] = True
            if st.button("→ 下一張", key="m012_next_btn"):
                st.session_state["m012_selected_idx"] = (sel_idx + 1) % n_items
                st.session_state["m012_kbd_nav"] = True

            if classification_labels:
                current_clf = classifications.get(item_id, "")

                # ── 幽靈分類按鈕（鍵盤 1-9 用，JS 會隱形化） ─────────────────
                _syms = ["①","②","③","④","⑤","⑥","⑦","⑧","⑨"]
                for _qi, _lbl in enumerate(classification_labels[:9]):
                    if st.button(f"{_syms[_qi]} {_lbl}", key=f"qc_{item_id}_{_qi}"):
                        _save_clf(workspace_dir, item_id, _lbl, classifications)
                        st.session_state["m012_selected_idx"] = _next_unclassified(
                            items, sel_idx, classifications
                        )
                        st.rerun()

                # selectbox（選即存）+ 重設
                # 前 9 個加 [1]…[9] 快捷鍵提示
                def _display(i: int, lbl: str) -> str:
                    return f"[{i+1}] {lbl}" if i < 9 else lbl

                clf_display = ["請選擇分類"] + [
                    _display(i, lbl) for i, lbl in enumerate(classification_labels)
                ]
                # 把 raw label 對應到 display 選項的索引
                clf_default = 0
                if current_clf:
                    for _di, _dlbl in enumerate(clf_display):
                        if current_clf in _dlbl:
                            clf_default = _di
                            break

                def _on_clf_change():
                    chosen = st.session_state.get(f"clf_sel_{item_id}", "請選擇分類")
                    if chosen == "請選擇分類":
                        return
                    # 從 "[1] 物件A" 還原為 "物件A"
                    import re as _re
                    raw = _re.sub(r"^\[\d+\] ", "", chosen)
                    _save_clf(workspace_dir, item_id, raw, classifications)
                    st.session_state["m012_selected_idx"] = _next_unclassified(
                        items, sel_idx, classifications
                    )

                sel_c2, reset_c2 = st.columns([5, 1])
                with sel_c2:
                    st.selectbox(
                        "分類", clf_display, index=clf_default,
                        key=f"clf_sel_{item_id}",
                        label_visibility="collapsed",
                        on_change=_on_clf_change,
                    )
                with reset_c2:
                    if current_clf and st.button(
                        "✕", use_container_width=True,
                        key=f"clf_reset_{item_id}",
                        help="清除分類",
                    ):
                        _clear_clf(workspace_dir, item_id, classifications)
                        st.rerun()

                st.divider()

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

                    with st.expander(f"標注明細（{len(shapes)} 個物件）", expanded=False):
                        rows = [
                            {
                                "Label":  s.get("label", "?"),
                                "Shape":  s.get("shape_type", "?"),
                                "Points": len(s.get("points", [])),
                            }
                            for s in shapes
                        ]
                        st.dataframe(rows, use_container_width=True, hide_index=True)
                else:
                    # ann_path 存在但 shapes 為空
                    _show_img(fp, enhance)
                    st.info("標注檔存在但尚無 shape，請以「🖊 標注工具」繼續標注。")
            else:
                # 無標注
                _show_img(fp, enhance)
                st.info("此圖尚無標注，點擊左側「🖊 標注工具」開始標注。")

