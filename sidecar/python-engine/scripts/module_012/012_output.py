from __future__ import annotations

"""
012_output.py — Annotation Session 輸出 UI。

master-detail 介面：
  左欄  — 圖片列表（縮圖 + 狀態篩選 + 選取 + 標注工具按鈕）
  右欄  — Detail Panel（原圖 vs 標注結果、標注明細 expander、上下張導覽）

* 標注 JSON 由 X-AnyLabeling 直接輸出到影像所在目錄（同名 .json）
* streamlit_autorefresh 可由 Input 頁設定間隔與啟停
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

def _json_matches_image(json_file: Path, target: Path) -> bool:
    """Return True when a LabelMe JSON either omits imagePath or points at target."""
    try:
        stored = json.loads(json_file.read_text(encoding="utf-8")).get("imagePath", "")
        if not stored:
            return True
        stored_path = Path(stored)
        if not stored_path.is_absolute():
            stored_path = json_file.parent / stored_path
        return stored_path.resolve() == target
    except Exception:
        return True


def _find_annotation(img_path: str) -> tuple[bool, str, int]:
    """回傳 (has_ann, ann_path, shape_count)。module_012 只讀影像同目錄同名 JSON。"""
    if not img_path:
        return False, "", 0

    target = Path(img_path).resolve()
    same_dir = Path(img_path).with_suffix(".json")
    if not (same_dir.exists() and _json_matches_image(same_dir, target)):
        return False, "", 0

    try:
        sc = len(json.loads(same_dir.read_text(encoding="utf-8")).get("shapes", []))
    except Exception:
        sc = 0
    return True, str(same_dir), sc


# ─── 標注狀態快取（session_state + mtime 增量更新） ──────────────────────────

PAGE_SIZE = 50


def _scan_items(db_items: list[dict]) -> tuple[list[dict], dict[str, float]]:
    """Full scan — 首次載入或 manifest 換新時呼叫。"""
    items: list[dict] = []
    mtimes: dict[str, float] = {}
    for it in db_items:
        fp = it.get("file_path", "")
        has_ann, ann_path, shape_count = _find_annotation(fp)
        items.append({**it, "has_ann": has_ann, "ann_path": ann_path, "shape_count": shape_count})
        if ann_path:
            try:
                mtimes[ann_path] = Path(ann_path).stat().st_mtime
            except Exception:
                mtimes[ann_path] = 0.0
    return items, mtimes


def _incremental_refresh(
    cached: list[dict], mtimes: dict[str, float]
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
                has_ann, new_ap, sc = _find_annotation(fp)
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
            # 尚無標注：只檢查影像同目錄同名 JSON。
            candidate = Path(fp).with_suffix(".json")
            if candidate.exists():
                has_ann, new_ap, sc = _find_annotation(fp)
                item["has_ann"] = has_ann
                item["ann_path"] = new_ap
                item["shape_count"] = sc
                if new_ap:
                    try:
                        new_mtimes[new_ap] = Path(new_ap).stat().st_mtime
                    except Exception:
                        new_mtimes[new_ap] = 0.0
    return cached, new_mtimes


def _get_items(manifest_id: str, db_items: list[dict]) -> list[dict]:
    """session_state 快取入口：cache miss → full scan；hit → incremental refresh。"""
    cached = st.session_state.get("m012_items")
    if (
        st.session_state.get("m012_cache_mid") != manifest_id
        or cached is None
        or len(cached) != len(db_items)
    ):
        items, mtimes = _scan_items(db_items)
        st.session_state["m012_items"]     = items
        st.session_state["m012_mtimes"]    = mtimes
        st.session_state["m012_cache_mid"] = manifest_id
        return items

    items, mtimes = _incremental_refresh(cached, st.session_state["m012_mtimes"])
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

    # Determine required version from pyvenv.cfg (e.g. "3.11" -> ver="3.11", short="311")
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


def _launch_xany(file_path: str, labels: list[str], classes_path: str,
                 xany_work_dir: str, xany_exe: str, ann_path: str = "") -> str | None:
    """以 X-AnyLabeling 開啟圖片（非阻塞），輸出到影像所在目錄。"""
    classes_txt = Path(classes_path) if classes_path else Path()
    out_dir = Path(file_path).parent

    xany_args = [
        "--filename", file_path,
        "--output", str(out_dir),
        "--work-dir", xany_work_dir,
        "--nodata", "--autosave", "--no-auto-update-check",
    ]
    if classes_txt.exists():
        xany_args += ["--labels", str(classes_txt), "--validatelabel", "exact"]

    # WDAC bypass strategy:
    #   xanylabeling.exe and some uv-created venv python.exe launchers may be blocked.
    #   Run X-AnyLabeling through a trusted Python with the same ABI as pyvenv.cfg,
    #   while pointing sys.path at the venv's site-packages.
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
                "【解決方法】請用已信任的 Python 重建 .venv-xanylabeling，例如：\n"
                "  python -m uv venv --python 3.11 --clear .venv-xanylabeling\n"
                "  python -m uv pip install --python .venv-xanylabeling\\Scripts\\python.exe --pre \"x-anylabeling-cvhub[cpu]\"\n"
                "重建後重啟應用程式即可自動使用 py -3.11 啟動。"
            )
        return str(e)


def _launch_labelme(file_path: str, classes_path: str, labelme_exe: str) -> str | None:
    """以 LabelMe 開啟圖片（非阻塞），輸出到影像同目錄同名 JSON。"""
    out_json = str(Path(file_path).with_suffix(".json"))
    classes_txt = Path(classes_path) if classes_path else Path()

    labelme_args = [
        file_path,
        "--output", out_json,
        "--nodata",
        "--autosave",
    ]
    if classes_txt.exists():
        labelme_args += ["--labels", str(classes_txt)]

    exe_path = Path(labelme_exe)
    if labelme_exe != "labelme" and (exe_path.parent / "python.exe").exists():
        cmd = [str(exe_path.parent / "python.exe"), "-m", "labelme"] + labelme_args
    else:
        cmd = [labelme_exe] + labelme_args

    try:
        subprocess.Popen(cmd)
        return None
    except Exception as e:
        return str(e)


def _launch_annotation_tool(
    annotation_tool: str,
    file_path: str,
    labels: list[str],
    classes_path: str,
    xany_work_dir: str,
    xany_exe: str,
    labelme_exe: str,
    ann_path: str = "",
) -> tuple[str, str | None]:
    """Launch selected annotation tool. Returns (display_name, error)."""
    if annotation_tool == "labelme":
        return "LabelMe", _launch_labelme(file_path, classes_path, labelme_exe)
    return "X-AnyLabeling", _launch_xany(
        file_path, labels, classes_path, xany_work_dir, xany_exe, ann_path=ann_path
    )


def _show_img(fp: str, enhance: bool) -> None:
    """Display image in right panel; apply contrast enhancement when enhance=True."""
    if enhance:
        try:
            st.image(_draw_annotations(fp, {}, enhance=True), use_container_width=True)
            return
        except Exception:
            pass
    st.image(fp, use_container_width=True)


def _right_panel_img(fp: str, enhance: bool, item_id: str = "") -> None:
    """右欄單張圖片顯示：支援 enhance 對比 + 🔍 放大按鈕（Streamlit dialog）。"""
    if enhance:
        try:
            img_bytes = _draw_annotations(fp, {}, enhance=True)
            st.image(img_bytes, use_container_width=True)
            if item_id and st.button("🔍 放大", key=f"zoom_e_{item_id}", use_container_width=True):
                st.session_state["_m012_zoom_data"] = (img_bytes, Path(fp).name)
                _zoom_dialog()
            return
        except Exception:
            pass
    st.image(fp, use_container_width=True)
    full = _make_full_jpeg(fp)
    if full and item_id:
        if st.button("🔍 放大", key=f"zoom_f_{item_id}", use_container_width=True):
            st.session_state["_m012_zoom_data"] = (full, Path(fp).name)
            _zoom_dialog()


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


# ─── 縮圖 HTML 片段（供 hover popup 使用） ───────────────────────────────────

@st.cache_data(show_spinner=False, max_entries=500)
def _make_preview(file_path: str) -> bytes | None:
    try:
        from PIL import Image, ImageOps
        img = ImageOps.exif_transpose(Image.open(file_path)).convert("RGB")
        img.thumbnail((640, 480), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
        return buf.getvalue()
    except Exception:
        return None


@st.cache_data(show_spinner=False, max_entries=500)
def _make_ann_preview(file_path: str, ann_path: str) -> bytes | None:
    try:
        label_data = json.loads(Path(ann_path).read_text(encoding="utf-8"))
        ann_bytes = _draw_annotations(file_path, label_data, enhance=False)
        from PIL import Image
        img = Image.open(io.BytesIO(ann_bytes)).convert("RGB")
        img.thumbnail((640, 480), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
        return buf.getvalue()
    except Exception:
        return None


@st.cache_data(show_spinner=False, max_entries=100)
def _make_full_jpeg(file_path: str) -> bytes | None:
    """高解析度原圖（lightbox 用），上限 1920×1440，JPEG。"""
    try:
        from PIL import Image, ImageOps
        img = ImageOps.exif_transpose(Image.open(file_path)).convert("RGB")
        img.thumbnail((1920, 1440), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=92)
        return buf.getvalue()
    except Exception:
        return None


@st.dialog("🔍 放大圖片", width="large")
def _zoom_dialog() -> None:
    """原生 Streamlit modal —— 顯示右欄圖片的全尺寸版本。"""
    data = st.session_state.get("_m012_zoom_data")
    if not data:
        return
    img_bytes, caption = data
    st.image(img_bytes, caption=caption, use_container_width=True)


def _thumb_html(thumb_bytes: bytes | None, img_path: str, tag: str,
                color: str, border: str, preview_bytes: bytes | None = None) -> str:
    if not thumb_bytes:
        return '<span style="color:#94a3b8;font-size:10px">—</span>'
    b64 = base64.b64encode(thumb_bytes).decode()
    p64 = base64.b64encode(preview_bytes or thumb_bytes).decode()
    return (
        f'<div class="m012-thumb" style="display:inline-block;text-align:center;position:relative;">'
        f'<img src="data:image/jpeg;base64,{b64}"'
        f' style="max-height:80px;width:auto;border-radius:5px;'
        f'border:2px solid {border};display:block;cursor:zoom-in;" />'
        f'<div class="m012-preview">'
        f'<img src="data:image/jpeg;base64,{p64}" />'
        f'<div style="margin-top:6px;font-size:12px;text-align:center;color:{color};'
        f'font-family:sans-serif;">{tag}</div>'
        f'</div>'
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

def _save_clf(manifest_id: str, item_id: str, label: str, cache: dict, file_path: str = "") -> None:
    if not manifest_id:
        return
    cache[item_id] = label
    _cfg.save_classifications(manifest_id, cache)
    # 同時以 file_path 為 key 存一份，跨 manifest 存活
    if file_path:
        _fp_clf = _cfg.load_classifications_by_path()
        _fp_clf[file_path] = label
        _cfg.save_classifications_by_path(_fp_clf)


def _clear_clf(manifest_id: str, item_id: str, cache: dict, file_path: str = "") -> None:
    if not manifest_id:
        return
    cache.pop(item_id, None)
    _cfg.save_classifications(manifest_id, cache)
    if file_path:
        _fp_clf = _cfg.load_classifications_by_path()
        _fp_clf.pop(file_path, None)
        _cfg.save_classifications_by_path(_fp_clf)


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
        # engine 重啟時會刪除 result JSON；嘗試從上次儲存的 config 自動重建
        _fallback_cfg = _cfg.load_config()
        _last_mid = _fallback_cfg.get("last_manifest_id", "")

        # 若 last_manifest_id 的 manifest 沒有分類，改找最近有分類的 manifest
        if _last_mid and not _cfg.load_classifications(_last_mid):
            _clf_dir = _cfg.get_classification_path("_dummy").parent
            _best_mid, _best_mtime = "", 0.0
            for _cf in _clf_dir.glob("module_012_classifications_*.json"):
                try:
                    _mt = _cf.stat().st_mtime
                    if _mt > _best_mtime and json.loads(_cf.read_text(encoding="utf-8")):
                        _best_mtime = _mt
                        _best_mid = _cf.stem.replace("module_012_classifications_", "")
                except Exception:
                    pass
            # 用 best_mid 的前 12 碼反查完整 manifest_id（從 DB）
            if _best_mid:
                try:
                    _db_path = _cfg.get_manifest_db_path()
                    _all = _mdb.list_manifests(_db_path)
                    _match = next((m["manifest_id"] for m in _all if m["manifest_id"][:12] == _best_mid), "")
                    if _match:
                        _last_mid = _match
                except Exception:
                    pass

        if _last_mid:
            _proc_spec = _ilu.spec_from_file_location("_012_process", _HERE / "012_process.py")
            _proc = _ilu.module_from_spec(_proc_spec)
            _proc_spec.loader.exec_module(_proc)
            result = _proc.execute_logic({
                "manifest_id": _last_mid,
                "annotation_tool": _fallback_cfg.get("annotation_tool", "x-anylabeling"),
                "labels": _fallback_cfg.get("annotation_labels", []),
                "classification_labels": _fallback_cfg.get("classification_labels", []),
                "autorefresh_enabled": _fallback_cfg.get("autorefresh_enabled", True),
                "autorefresh_seconds": _fallback_cfg.get("autorefresh_seconds", 10),
            })
            mode = result.get("mode", "idle")
        if mode != "ready":
            st.info("請在 Input 頁面選擇 Manifest 與標注類別，點選「▶ 執行」開始工作階段。")
            return

    manifest_id            = result.get("manifest_id", "")
    manifest_name          = result.get("manifest_name", "")
    labels                 = result.get("labels", [])
    annotation_tool        = result.get("annotation_tool", "x-anylabeling")
    classification_labels  = result.get("classification_labels", [])
    xany_exe               = result.get("xany_exe", "xanylabeling")
    labelme_exe            = result.get("labelme_exe", "labelme")
    classes_path           = result.get("classes_path", "")
    xany_work_dir          = result.get("xany_work_dir", "")
    cfg                    = _cfg.load_config()
    autorefresh_enabled    = bool(result.get("autorefresh_enabled", cfg.get("autorefresh_enabled", True)))
    autorefresh_seconds    = int(result.get("autorefresh_seconds", cfg.get("autorefresh_seconds", 10)) or 10)
    autorefresh_seconds    = max(5, min(300, autorefresh_seconds))

    if autorefresh_enabled:
        st_autorefresh(
            interval=autorefresh_seconds * 1000,
            key="m012_annotation_autorefresh",
        )

    # 每次 rerun 從磁碟重讀分類結果（per-manifest + file_path 兩層合併）
    classifications: dict[str, str] = _cfg.load_classifications(manifest_id) if manifest_id else {}
    # file_path-based 分類（跨 manifest 存活），待 items 載入後 merge
    _fp_clf: dict[str, str] = _cfg.load_classifications_by_path()

    # 注入鍵盤快捷鍵
    _keyboard_listener()

    # ── CSS ──────────────────────────────────────────────────────────────────
    st.markdown("""<style>
[data-testid='stImage'] img { max-height: 58vh; width: auto !important; object-fit: contain; }
.thumb-selected { border: 3px solid #1a73e8 !important; border-radius: 6px; padding: 2px; }
.m012-preview {
    display: none;
    position: fixed;
    left: min(46vw, 760px);
    top: 92px;
    z-index: 2147483000;
    max-width: min(46vw, 680px);
    background: #fff;
    border: 1.5px solid #94a3b8;
    border-radius: 8px;
    padding: 10px;
    box-shadow: 0 10px 36px rgba(15, 23, 42, .28);
    pointer-events: none;
}
.m012-preview img {
    display: block;
    max-width: min(44vw, 640px);
    max-height: 70vh;
    width: auto;
    height: auto;
    border-radius: 4px;
}
.m012-thumb:hover .m012-preview { display: block; }
</style>""", unsafe_allow_html=True)

    # ── 標注狀態：session_state 快取 + mtime 增量更新 ─────────────────────────
    db_path = _cfg.get_manifest_db_path()
    try:
        db_items = _mdb.get_manifest_items(db_path, manifest_id)
    except Exception:
        db_items = result.get("items", [])

    items     = _get_items(manifest_id, db_items)
    annotated = sum(1 for it in items if it["has_ann"])
    total     = len(items)

    # 用 file_path-based 分類補齊目前 manifest 沒有分類的項目
    if _fp_clf:
        for _it in items:
            _iid = _it.get("item_id", "")
            if _iid and _iid not in classifications:
                _fp = _it.get("file_path", "")
                if _fp and _fp in _fp_clf:
                    classifications[_iid] = _fp_clf[_fp]

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
    if autorefresh_enabled:
        st.caption(f"自動重新掃描：每 {autorefresh_seconds} 秒")
    else:
        st.caption("自動重新掃描：已關閉")

    refresh_c, update_c = st.columns([1, 1])
    with refresh_c:
        if st.button("重新掃描標注", key="m012_refresh_annotations", use_container_width=True):
            st.session_state.pop("m012_items", None)
            st.session_state.pop("m012_mtimes", None)
            st.session_state.pop("m012_cache_mid", None)
            st.rerun()
    with update_c:
        if st.button("📁 前往 Update →", type="primary", key="m012_goto_update", use_container_width=True):
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
                preview_bytes = _make_preview(fp) if fp else None
                ann_thumb_bytes = (
                    _make_ann_thumb(fp, item["ann_path"])
                    if has_ann and item["ann_path"] else None
                )
                ann_preview_bytes = (
                    _make_ann_preview(fp, item["ann_path"])
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
                            preview_bytes=preview_bytes,
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
                            preview_bytes=ann_preview_bytes,
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
                            st.session_state["m012_selected_idx"] = global_idx
                            tool_name, err = _launch_annotation_tool(
                                annotation_tool, fp, labels, classes_path,
                                xany_work_dir, xany_exe, labelme_exe,
                                ann_path=item["ann_path"],
                            )
                            if err:
                                st.error(f"啟動失敗：{err}")
                            else:
                                st.toast(f"{tool_name} 已開啟：{fname}", icon="🖊")
                            st.rerun()

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
                        _save_clf(manifest_id, item_id, _lbl, classifications, file_path=fp)
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
                    _save_clf(manifest_id, item_id, raw, classifications, file_path=fp)
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
                        _clear_clf(manifest_id, item_id, classifications, file_path=fp)
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
                        st.markdown("**原圖**")
                        st.image(fp, use_container_width=True)
                        orig_full = _make_full_jpeg(fp)
                        if orig_full and st.button("🔍 放大原圖", key=f"zoom_o_{item_id}", use_container_width=True):
                            st.session_state["_m012_zoom_data"] = (orig_full, "原圖")
                            _zoom_dialog()
                    with ann_c:
                        st.markdown("**標注結果**")
                        try:
                            ann_bytes = _draw_annotations(fp, label_data, enhance=enhance)
                            st.image(ann_bytes, use_container_width=True)
                            if st.button("🔍 放大標注", key=f"zoom_a_{item_id}", use_container_width=True):
                                st.session_state["_m012_zoom_data"] = (ann_bytes, "標注結果")
                                _zoom_dialog()
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
                    _right_panel_img(fp, enhance, item_id=item_id)
                    st.info("標注檔存在但尚無 shape，請以「🖊 標注工具」繼續標注。")
            else:
                # 無標注
                _right_panel_img(fp, enhance, item_id=item_id)
                st.info("此圖尚無標注，點擊左側「🖊 標注工具」開始標注。")
