from __future__ import annotations

import io
import json
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps

try:
    from db_utils import SimpleDAO
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools"))
    from db_utils import SimpleDAO

try:
    from _config import get_annotation_labels
except ImportError:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _config import get_annotation_labels

_SELECT_COLS = "id, filename, file_type, image_time, true_label, classification, tagged_at"
LABEL_OPTIONS = ["請選擇分類", "貓", "狗", "大象", "unknown"]

_PALETTE = [
    (255, 80,  80),
    (80,  180, 255),
    (80,  220, 80),
    (255, 200, 60),
    (200, 80,  255),
]

_THUMB_SIZE = (120, 90)

_CJK_FONTS = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msjh.ttc",
    "C:/Windows/Fonts/mingliu.ttc",
    "C:/Windows/Fonts/simsun.ttc",
]


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
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
    """Estimate pixel width of label text (CJK chars are wider)."""
    return sum(font_size for c in text if ord(c) > 127) + sum(int(font_size * 0.6) for c in text if ord(c) <= 127) + 8


# ── annotation helpers ────────────────────────────────────────────────────────

def _load_label_json(labels_dir: Path | None, image_filename: str) -> dict | None:
    if not labels_dir:
        return None
    stem = Path(image_filename).stem
    p = labels_dir / f"{stem}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _annotation_objects(label_data: dict | None) -> list[dict]:
    if not label_data:
        return []
    if "objects" in label_data:
        return [
            {
                "label": obj.get("category", ""),
                "shape_type": "polygon",
                "points": obj.get("segmentation", []),
                "bbox": obj.get("bbox", []),
            }
            for obj in label_data.get("objects", [])
        ]
    return label_data.get("shapes", [])


def _draw_annotations(img_path: Path, label_data: dict, enhance: bool = False) -> bytes:
    img = ImageOps.exif_transpose(Image.open(img_path)).convert("RGB")
    if enhance:
        img = ImageEnhance.Contrast(img).enhance(2.2)
        img = ImageEnhance.Color(img).enhance(1.8)
    draw = ImageDraw.Draw(img)
    fs   = max(14, img.height // 22)
    font = _get_font(fs)

    colour_map: dict[str, tuple] = {}
    for shape in _annotation_objects(label_data):
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


def _enhance_image(img_path: Path) -> bytes:
    img = ImageOps.exif_transpose(Image.open(img_path)).convert("RGB")
    img = ImageEnhance.Contrast(img).enhance(2.2)
    img = ImageEnhance.Color(img).enhance(1.8)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _save_enhanced_for_xany(img_path: Path, labels_dir: Path) -> Path:
    """Save contrast-enhanced image to images_enhanced/ with same filename for X-AnyLabeling."""
    enhanced_dir = labels_dir.parent / "images_enhanced"
    enhanced_dir.mkdir(parents=True, exist_ok=True)
    dest = enhanced_dir / img_path.name
    dest.write_bytes(_enhance_image(img_path))
    return dest


def _launch_xany_single(
    img_path: Path,
    labels_dir: Path,
    workspace_root: str,
    enhance: bool = False,
) -> str | None:
    """Launch X-AnyLabeling for a single image. Returns error string or None.

    When enhance=True, a contrast-enhanced copy is saved to images_enhanced/ and
    X-AnyLabeling opens that copy. Label coordinates are identical (same dimensions)
    so Phase 2 import works unchanged.
    """
    import subprocess
    import os
    candidates = [
        Path(os.environ.get("XANYLABELING_EXE", "")),
        Path(workspace_root).parents[3] / ".venv-xanylabeling" / "Scripts" / "xanylabeling.exe",
    ]
    exe = next((str(c) for c in candidates if str(c) and c.exists()), "xanylabeling")
    labels_dir.mkdir(parents=True, exist_ok=True)
    xany_root = labels_dir.parent
    classes_txt = xany_root / "classes.txt"

    target = _save_enhanced_for_xany(img_path, labels_dir) if enhance else img_path

    exe_path = Path(exe)
    if exe_path.name.lower().startswith("xanylabeling") and (exe_path.parent / "python.exe").exists():
        cmd = [str(exe_path.parent / "python.exe"), "-m", "anylabeling.app"]
    else:
        cmd = [exe]
    cmd += [
        "--filename", str(target),
        "--output", str(labels_dir),
        "--work-dir", str(xany_root / ".xanylabeling"),
        "--nodata", "--autosave", "--no-auto-update-check",
    ]
    if classes_txt.exists():
        cmd += ["--labels", str(classes_txt), "--validatelabel", "exact"]
    try:
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        env["PYTHONNOUSERSITE"] = "1"
        if exe != "xanylabeling":
            env["PATH"] = str(Path(exe).resolve().parent) + os.pathsep + env.get("PATH", "")
        subprocess.Popen(cmd, env=env)
        return None
    except Exception as e:
        return str(e)


def _make_thumb(img_path: Path) -> bytes:
    img = ImageOps.exif_transpose(Image.open(img_path)).convert("RGB")
    img.thumbnail(_THUMB_SIZE, Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75)
    return buf.getvalue()


def _resolve_labels_dir(workspace_root: str) -> Path | None:
    if not workspace_root:
        return None
    session_file = Path(workspace_root) / "session.json"
    if not session_file.exists():
        return None
    try:
        session = json.loads(session_file.read_text(encoding="utf-8"))
        ld = Path(session.get("labels_dir", ""))
        return ld if ld.exists() else None
    except Exception:
        return None


def _load_session_full(workspace_root: str) -> dict | None:
    session_file = Path(workspace_root) / "session.json"
    if not session_file.exists():
        return None
    try:
        return json.loads(session_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def _keyboard_listener() -> None:
    """Inject a keyboard shortcut listener that clicks Streamlit buttons by text."""
    components.html("""
<script>
(function() {
    if (window.parent._kb006_active) return;
    window.parent._kb006_active = true;

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
        if (k === 'ArrowDown' || k === 'j') { e.preventDefault(); clickByText('→ 跳過'); }
        else if (k === 'ArrowUp' || k === 'k') { e.preventDefault(); clickByText('← 上一張'); }
        else if (k === 'Enter') { e.preventDefault(); clickByText('✅ 確認'); }
        else if (k === 'Tab') { e.preventDefault(); clickByText('→ 跳過'); }
        else if (k === '1') { e.preventDefault(); clickByText('①'); }
        else if (k === '2') { e.preventDefault(); clickByText('②'); }
        else if (k === '3') { e.preventDefault(); clickByText('③'); }
        else if (k === '4') { e.preventDefault(); clickByText('④'); }
        else if (k === 'c' || k === 'C') {
            var inputs = window.parent.document.querySelectorAll('input[type="checkbox"]');
            for (var inp of inputs) {
                var container = inp.closest('label') || inp.parentElement;
                if (container && container.textContent.indexOf('強化對比') >= 0) { inp.click(); break; }
            }
        }
    }, true);
})();
</script>
""", height=0)


def _do_browse_export(workspace: str, export_formats: list[str], approve: bool) -> None:
    session = _load_session_full(workspace)
    if not session:
        st.error("找不到 session.json，請先執行步驟 2 建立標注專案。")
        return
    import importlib.util
    _PROCESS_FILE = Path(__file__).parent / "006_process.py"
    spec = importlib.util.spec_from_file_location("_006_process", _PROCESS_FILE)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    p2 = mod.execute_logic({
        "mode":           "labeling_phase2",
        "workspace_root": workspace,
        "dataset_id":     session["dataset_id"],
        "schema_id":      session["schema_id"],
        "labels_dir":     session.get("labels_dir", ""),
        "annotation_format": session.get("annotation_format", "x-anylabeling"),
        "approve":        approve,
        "export_formats": export_formats,
    })
    _render_xany_phase2(p2)


def _image_status(filename: str, labels_dir: Path | None, classification: str | None) -> str:
    """Return a short status string for display."""
    has_ann = False
    if labels_dir:
        stem = Path(filename).stem
        lp = labels_dir / f"{stem}.json"
        if lp.exists():
            try:
                d = json.loads(lp.read_text(encoding="utf-8"))
                has_ann = len(_annotation_objects(d)) > 0
            except Exception:
                pass

    if classification:
        return "✅ 已驗收" if has_ann else "🏷 已分類"
    if has_ann:
        return "📦 待驗收"
    return "⏳ 待標注"


# ── DB helpers ────────────────────────────────────────────────────────────────

def _query_records(db_path: str, category_filter: str) -> list[dict]:
    dao = SimpleDAO(db_path)
    if category_filter == "ALL":
        return dao.query(f"SELECT {_SELECT_COLS} FROM images ORDER BY id")
    return dao.query(
        f"SELECT {_SELECT_COLS} FROM images WHERE true_label = ? ORDER BY id",
        (category_filter,),
    )


def _update_tag(db_path: str, record_id: int, classification: str) -> None:
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    SimpleDAO(db_path).execute(
        "UPDATE images SET classification = ?, tagged_at = ? WHERE id = ?",
        (classification, now, record_id),
    )


def _clear_tag(db_path: str, record_id: int) -> None:
    SimpleDAO(db_path).execute(
        "UPDATE images SET classification = NULL, tagged_at = NULL WHERE id = ?",
        (record_id,),
    )


def _next_untagged_index(records: list[dict], current_idx: int) -> int:
    for offset in range(1, len(records)):
        idx = (current_idx + offset) % len(records)
        if records[idx]["classification"] is None:
            return idx
    return (current_idx + 1) % len(records)


# ── browse mode ───────────────────────────────────────────────────────────────

def _render_browse(result: dict) -> None:
    db_path    = result["db_path"]
    image_dir  = Path(result["image_dir"])
    category   = result.get("filter", "ALL")
    workspace  = result.get("workspace_root", "")
    labels_dir = _resolve_labels_dir(workspace)

    # CSS: image max height + selected thumbnail highlight
    st.markdown("""<style>
[data-testid='stImage'] img { max-height: 58vh; width: auto !important; object-fit: contain; }
.thumb-selected { border: 3px solid #1a73e8; border-radius: 6px; padding: 2px; }
</style>""", unsafe_allow_html=True)

    _keyboard_listener()

    records = _query_records(db_path, category)
    if not records:
        st.warning(f"沒有找到「{category}」類別的資料。")
        return

    # ── project status bar ────────────────────────────────────────────────────
    total        = len(records)
    tagged_count = sum(1 for r in records if r["classification"] is not None)
    ann_count    = 0
    if labels_dir:
        for r in records:
            ld = _load_label_json(labels_dir, r["filename"])
            if ld and _annotation_objects(ld):
                ann_count += 1

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("總圖數",      total)
    m2.metric("X-Any 標注", f"{ann_count}/{total}")
    m3.metric("分類已完成",  f"{tagged_count}/{total}")
    pct = int(tagged_count / total * 100) if total else 0
    m4.metric("整體進度",    f"{pct}%")
    st.progress(pct / 100)

    with st.expander("📖 狀態說明", expanded=False):
        st.markdown(
            "⏳ **待標注** — 尚未有 X-AnyLabeling 標注框，也未人工分類  \n"
            "📦 **待驗收** — X-AnyLabeling 已標框，等待人工確認  \n"
            "🏷 **已分類** — 人工已選分類，但尚無標注框  \n"
            "✅ **已驗收** — 有標注框且人工已確認分類"
        )

    # ── auto-refresh controls ─────────────────────────────────────────────────
    if labels_dir:
        ar_col, num_col, _ = st.columns([2, 1, 5])
        with ar_col:
            auto_refresh = st.toggle(
                "🔄 自動更新",
                value=st.session_state.get("auto_refresh", True),
                key="auto_refresh",
            )
        with num_col:
            refresh_interval = st.number_input(
                "間隔（秒）",
                min_value=5,
                max_value=300,
                value=st.session_state.get("refresh_interval", 30),
                step=5,
                key="refresh_interval",
                label_visibility="collapsed",
                disabled=not auto_refresh,
            )

    st.divider()

    if "selected_idx" not in st.session_state:
        st.session_state.selected_idx = 0

    # read enhance toggle from previous render cycle so thumbnail-grid button can use it
    _sel_idx = int(st.session_state.get("selected_idx", 0))
    _enhance_active = False
    if records and 0 <= _sel_idx < len(records):
        _enhance_active = bool(st.session_state.get(f"enhance_{records[_sel_idx]['id']}", False))

    # ── main layout: thumbnail grid left | detail right ───────────────────────
    left_col, right_col = st.columns([1, 2], gap="medium")

    with left_col:
        st.markdown("**圖片列表**")
        f_status_col, f_cat_col = st.columns(2)
        with f_status_col:
            filter_status = st.selectbox(
                "狀態篩選",
                ["全部狀態", "⏳ 待標注", "📦 待驗收", "🏷 已分類", "✅ 已驗收"],
                label_visibility="collapsed",
            )
        with f_cat_col:
            _ANIMAL_CATS = ["ALL", "貓", "狗", "大象"]
            cat_default = _ANIMAL_CATS.index(category) if category in _ANIMAL_CATS else 0
            filter_cat = st.selectbox(
                "類別篩選", _ANIMAL_CATS, index=cat_default,
                label_visibility="collapsed",
            )
        if filter_cat != category:
            records = _query_records(db_path, filter_cat)

        for i, rec in enumerate(records):
            status = _image_status(rec["filename"], labels_dir, rec["classification"])
            if filter_status != "全部狀態" and filter_status not in status:
                continue

            is_selected = (i == st.session_state.selected_idx)
            img_path    = image_dir / rec["filename"]

            thumb_col, info_col = st.columns([1, 2])
            with thumb_col:
                if img_path.exists():
                    thumb = _make_thumb(img_path)
                    if is_selected:
                        st.markdown('<div class="thumb-selected">', unsafe_allow_html=True)
                    st.image(thumb, use_container_width=True)
                    if is_selected:
                        st.markdown('</div>', unsafe_allow_html=True)
                else:
                    st.markdown("🖼️")
            with info_col:
                fname = rec["filename"]
                if is_selected:
                    st.markdown(f"<span data-kb-selected='true' style='color:#1a73e8;font-weight:700'>▶ {fname}</span>",
                                unsafe_allow_html=True)
                else:
                    st.markdown(fname)
                st.caption(f"{status}　{rec.get('true_label', '')}")
                sel_col, ann_btn_col = st.columns(2)
                with sel_col:
                    if st.button("選取", key=f"sel_{i}",
                                 type="primary" if is_selected else "secondary",
                                 use_container_width=True):
                        st.session_state.selected_idx = i
                        st.rerun()
                with ann_btn_col:
                    _ann_help = (
                        "開啟 X-AnyLabeling 以強化對比圖標注（目前已啟用強化對比）"
                        if _enhance_active else
                        "開啟 X-AnyLabeling 對此圖畫標注框"
                    )
                    if st.button("🖊 標注工具", key=f"ann_{i}", use_container_width=True,
                                 help=_ann_help):
                        if labels_dir:
                            # Always sync classes.txt from shared config before launching
                            xany_root = labels_dir.parent
                            classes_txt = xany_root / "classes.txt"
                            ann_labels = get_annotation_labels()
                            if ann_labels:
                                xany_root.mkdir(parents=True, exist_ok=True)
                                classes_txt.write_text(
                                    "\n".join(ann_labels), encoding="utf-8"
                                )
                            err = _launch_xany_single(
                                img_path, labels_dir, workspace, enhance=_enhance_active,
                            )
                            if err:
                                st.error(f"啟動失敗：{err}")
                            elif _enhance_active:
                                st.info("已開啟強化對比圖進行標注，座標與原圖相同。")
                        else:
                            st.warning("尚未建立標注專案，請先執行步驟 2。")

        # Scroll the selected thumbnail into view after every rerun.
        # Uses data-kb-selected attribute for reliable targeting.
        components.html("""<script>
setTimeout(function() {
    var el = window.parent.document.querySelector('[data-kb-selected="true"]');
    if (el) { el.scrollIntoView({block: 'nearest', behavior: 'smooth'}); }
}, 400);
</script>""", height=0)

    # ── detail panel ──────────────────────────────────────────────────────────
    with right_col:
        selected_idx = int(st.session_state.selected_idx)
        if selected_idx >= len(records):
            selected_idx = 0
        selected = records[selected_idx]

        img_path   = image_dir / selected["filename"]
        label_data = _load_label_json(labels_dir, selected["filename"]) if labels_dir else None
        shapes     = _annotation_objects(label_data) if label_data else []

        # ── keyboard shortcut hint ────────────────────────────────────────────
        st.caption("⌨️ ↑/K 上一張　↓/J 下一張　1-4 快速分類　Enter 確認　Tab 跳過　C 對比")

        # ── classification controls at top ────────────────────────────────────
        current_cls = selected["classification"]
        if current_cls:
            st.markdown(f"**目前分類：** 🏷 `{current_cls}`")
        else:
            st.markdown("**目前分類：** 📋 尚未分類")

        # quick-confirm row (keyboard: 1-4)
        _QUICK = [("①", "貓"), ("②", "狗"), ("③", "大象"), ("④", "unknown")]
        q_cols = st.columns(4)
        for qi, (sym, lbl) in enumerate(_QUICK):
            display = "unk" if lbl == "unknown" else lbl
            with q_cols[qi]:
                if st.button(f"{sym} {display}", key=f"qc_{selected['id']}_{qi}",
                             use_container_width=True,
                             help=f"快速確認為「{lbl}」並跳至下一張（快捷鍵 {qi+1}）"):
                    _update_tag(db_path, selected["id"], lbl)
                    st.toast(f"🏷 {selected['filename']} → {lbl}", icon="✅")
                    refreshed = _query_records(db_path, filter_cat)
                    st.session_state.selected_idx = _next_untagged_index(refreshed, selected_idx)
                    st.rerun()

        # selectbox + confirm / prev / skip / reset
        cls_default = LABEL_OPTIONS.index(current_cls) if current_cls in LABEL_OPTIONS else 0
        tag_col, btn_col, prev_col, skip_col, reset_col = st.columns([3, 1, 1, 1, 1])
        with tag_col:
            tag_choice = st.selectbox(
                "分類", LABEL_OPTIONS,
                index=cls_default,
                key=f"tag_{selected['id']}", label_visibility="collapsed",
            )
        with btn_col:
            if st.button("✅ 確認", type="primary", use_container_width=True,
                         help="儲存分類並跳至下一張未分類圖片 (Enter)"):
                if tag_choice == "請選擇分類":
                    st.warning("請先從下拉選單選擇動物類別。")
                else:
                    _update_tag(db_path, selected["id"], tag_choice)
                    st.toast(f"🏷 {selected['filename']} → {tag_choice}", icon="✅")
                    refreshed = _query_records(db_path, filter_cat)
                    next_idx  = _next_untagged_index(refreshed, selected_idx)
                    st.session_state.selected_idx = next_idx
                    st.rerun()
        with prev_col:
            if st.button("← 上一張", use_container_width=True,
                         help="回到上一張（快捷鍵 ↑/K）"):
                st.session_state.selected_idx = (selected_idx - 1) % len(records)
                st.rerun()
        with skip_col:
            if st.button("→ 跳過", use_container_width=True,
                         help="暫時跳過，稍後可返回（快捷鍵 ↓/J/Tab）"):
                st.session_state.selected_idx = (selected_idx + 1) % len(records)
                st.rerun()
        with reset_col:
            if current_cls and st.button("✕ 重設", use_container_width=True,
                                          help="清除已儲存的分類，回到待分類狀態"):
                _clear_tag(db_path, selected["id"])
                st.rerun()

        st.divider()

        # ── image display ─────────────────────────────────────────────────────
        enhance = st.toggle(
            "🔆 強化對比（僅標注結果）", key=f"enhance_{selected['id']}",
            help="僅對右側標注結果圖套用對比度與飽和度強化，原圖保持不變。"
                 "可用於辨識顏色細微差異或表面瑕疵。",
        )

        if not img_path.exists():
            st.warning(f"找不到影像：{img_path}")
        elif shapes:
            orig_col, ann_col = st.columns(2)
            with orig_col:
                st.markdown("**原圖**（未修改）")
                st.image(str(img_path), use_container_width=True)
            with ann_col:
                ann_label = "**標注結果 🔆**（強化對比）" if enhance else "**標注結果**"
                st.markdown(ann_label)
                ann_bytes = _draw_annotations(img_path, label_data, enhance=enhance)
                st.image(ann_bytes, use_container_width=True)

            with st.expander("標注明細", expanded=True):
                rows = [
                    {"Label": s.get("label", "?"),
                     "Shape": s.get("shape_type", "?"),
                     "Points": len(s.get("points", []))}
                    for s in shapes
                ]
                st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.image(str(img_path), use_container_width=True)
            if labels_dir:
                st.info("此圖尚無 X-AnyLabeling 標注框。點擊左側「🖊 標注工具」開始標注。")

    # ── export panel ─────────────────────────────────────────────────────────
    session = _load_session_full(workspace)
    if session:
        with st.expander("📦 匯出訓練資料", expanded=False):
            ann_count_for_export = 0
            labels_dir_export = Path(session.get("labels_dir", ""))
            if labels_dir_export.exists():
                for jf in labels_dir_export.glob("*.json"):
                    if jf.name in {"manifest.json", "conversion_report.json"}:
                        continue
                    try:
                        if _annotation_objects(json.loads(jf.read_text(encoding="utf-8"))):
                            ann_count_for_export += 1
                    except Exception:
                        pass
            st.info(f"labels/ 目錄中已有標注的圖片：**{ann_count_for_export}** 張")
            exp_col1, exp_col2 = st.columns(2)
            with exp_col1:
                export_formats_sel = st.multiselect(
                    "匯出格式", ["coco", "yolo-detection", "yolo-segmentation", "labelme", "x-anylabeling", "isat"],
                    default=["coco", "yolo-detection"],
                    key="browse_export_formats",
                )
            with exp_col2:
                export_approve = st.checkbox("自動 Approve", value=True,
                                             key="browse_export_approve")
            if st.button("開始匯出", type="primary", key="browse_export_btn",
                         disabled=ann_count_for_export == 0):
                _do_browse_export(
                    workspace,
                    export_formats_sel or ["coco", "yolo-detection"],
                    export_approve,
                )

    # ── auto-refresh while X-AnyLabeling session is active ───────────────────
    if labels_dir and st.session_state.get("auto_refresh", True):
        interval = int(st.session_state.get("refresh_interval", 30))
        st_autorefresh(interval=interval * 1000, key="browse_autorefresh")


def _do_inline_import(
    phase1_result: dict,
    export_formats: list[str] | None = None,
) -> None:
    """Called when user clicks '立即匯入' in Phase 1 output."""
    import importlib.util
    _PROCESS_FILE = Path(__file__).parent / "006_process.py"
    spec = importlib.util.spec_from_file_location("_006_process", _PROCESS_FILE)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    pf = phase1_result.get("project_files", {})
    p2 = mod.execute_logic({
        "mode":           "labeling_phase2",
        "workspace_root": phase1_result["workspace_root"],
        "dataset_id":     phase1_result["dataset"]["id"],
        "schema_id":      phase1_result["schema"]["id"],
        "labels_dir":     pf.get("labels_dir", ""),
        "annotation_format": phase1_result.get("annotation_format", "x-anylabeling"),
        "approve":        True,
        "export_formats": export_formats or ["coco", "yolo-detection"],
    })
    _render_xany_phase2(p2)


# ── phase 1 output (live sync) ────────────────────────────────────────────────

def _render_xany_phase1(r: dict) -> None:
    if r.get("error"):
        _error_map = {
            "db_not_found":    "找不到資料庫。",
            "no_images":       f"類別「{r.get('category')}」中沒有圖片。",
            "no_images_found": "圖片檔案不存在於影像目錄中。",
        }
        st.error(_error_map.get(r["error"], r["error"]))
        return

    tool_name  = r.get("annotation_tool", "x-anylabeling")
    install    = r.get("tool_install") or r.get("xany_install") or {}
    pf         = r.get("project_files", {})
    labels_dir = Path(pf.get("labels_dir", "")) if pf.get("labels_dir") else None
    images_dir = Path(r.get("project_dir", r.get("xany_dir", ""))) / "images"

    # ── project summary ───────────────────────────────────────────────────────
    st.subheader("標注專案已準備完成")
    st.caption(
        f"類別：{r['category']}　｜　"
        f"Workspace：`{r['workspace_root']}`　｜　"
        f"X-AnyLabeling {install.get('version', 'not found')}"
    )

    # ── live progress ─────────────────────────────────────────────────────────
    image_names  = sorted(p.name for p in images_dir.glob("*") if p.is_file()) if images_dir.exists() else []
    status_rows  = []
    total_shapes = 0

    for img_name in image_names:
        ld     = _load_label_json(labels_dir, img_name)
        shapes = _annotation_objects(ld) if ld else []
        n      = len(shapes)
        total_shapes += n
        labels_seen = list({s.get("label", "") for s in shapes if s.get("label")})
        status_rows.append({
            "圖片":   img_name,
            "狀態":   "✅ 已標注" if n > 0 else "⏳ 待標注",
            "標注數": n,
            "Labels": ", ".join(labels_seen) if labels_seen else "—",
        })

    done  = sum(1 for s in status_rows if "✅" in s["狀態"])
    total = len(status_rows)
    pct   = int(done / total * 100) if total else 0

    m1, m2, m3 = st.columns(3)
    m1.metric("已完成",   f"{done} / {total}")
    m2.metric("進度",     f"{pct}%")
    m3.metric("總標注數", total_shapes)

    st.progress(pct / 100)

    # completion banner
    if total > 0 and done == total:
        st.success("🎉 所有圖片標注完成！")
        imp_col, note_col = st.columns([1, 3])
        with imp_col:
            if st.button("⚡ 立即匯入並匯出", type="primary", use_container_width=True,
                         help="自動 approve 並匯出 COCO + YOLO，不需切換步驟 3"):
                st.session_state["confirm_inline_import"] = True
        with note_col:
            st.caption("匯入後自動 Approve + 匯出 COCO / YOLO。或切換至步驟 3 自訂選項。")

        if st.session_state.get("confirm_inline_import"):
            st.warning(f"⚠️ 將匯入 **{done}** 張圖的標注框並自動 Approve。請選擇匯出格式：")
            fmt_col, yes_col, no_col = st.columns([3, 1, 1])
            with fmt_col:
                inline_formats = st.multiselect(
                    "匯出格式", ["coco", "yolo-detection", "yolo-segmentation", "labelme", "x-anylabeling", "isat"],
                    default=["coco", "yolo-detection"],
                    key="inline_export_formats",
                    label_visibility="collapsed",
                )
            with yes_col:
                if st.button("✅ 確定匯入", type="primary", use_container_width=True):
                    st.session_state.pop("confirm_inline_import", None)
                    _do_inline_import(r, export_formats=inline_formats or ["coco", "yolo-detection"])
                    return
            with no_col:
                if st.button("取消", use_container_width=True):
                    st.session_state.pop("confirm_inline_import", None)
                    st.rerun()
    elif done > 0:
        st.info(f"標注進行中，已完成 {done}/{total}。X-AnyLabeling 存檔後此頁自動更新。")
    else:
        st.warning("尚未偵測到標注檔案。請開啟 X-AnyLabeling 開始標注。")

    if status_rows:
        st.dataframe(status_rows, use_container_width=True, hide_index=True)

    # launch command
    st.divider()
    launch = r.get("tool_launch") or r.get("xany_launch") or {}
    if launch.get("launched"):
        st.success("X-AnyLabeling 已啟動。")
        st.code(" ".join(str(c) for c in launch.get("command", [])), language="text")
    else:
        if pf.get("labels_dir"):
            xany_root = Path(pf["labels_dir"]).parent
            exe = install.get("executable", "xanylabeling")
            with st.expander("手動啟動指令", expanded=False):
                st.code(
                    f'{exe} --filename "{xany_root / "images"}" '
                    f'--output "{xany_root / "labels"}" '
                    f'--work-dir "{xany_root / ".xanylabeling"}" '
                    f'--nodata --autosave --no-auto-update-check '
                    f'--labels "{xany_root / "classes.txt"}" --validatelabel exact',
                    language="text",
                )

    with st.expander("專案詳細資訊", expanded=False):
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**classes.txt**")
            st.code(pf.get("classes_txt", ""), language="text")
        with col_b:
            st.markdown(f"**images/**（{len(pf.get('images', []))} 張）")
            for name in pf.get("images", []):
                st.text(f"  {name}")
        st.json({"dataset": r["dataset"], "schema": r["schema"]}, expanded=False)

    # live poll — uses same interval as browse auto-refresh setting
    if st.session_state.get("auto_refresh", True):
        interval = int(st.session_state.get("refresh_interval", 30))
        st_autorefresh(interval=interval * 1000, key="phase1_autorefresh")


# ── phase 2 output ────────────────────────────────────────────────────────────

def _render_xany_phase2(r: dict) -> None:
    aset       = r["annotation_set"]
    validation = r["validation"]
    imp        = r.get("import_result", {})

    st.subheader("標注已匯入並匯出")
    state_label = {"approved": "✅ 已驗收", "submitted": "📋 待審核", "draft": "📝 草稿"}.get(
        aset.get("state", ""), aset.get("state", "-")
    )
    st.caption(
        f"耗時 {r['elapsed_ms']:.0f} ms　｜　"
        f"專案狀態：{state_label}　｜　"
        f"Workspace：`{r['workspace_root']}`"
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("匯入標注數",  imp.get("matched_count", 0))
    col2.metric("驗證結果",    "✅ 通過" if validation.get("ok") else "❌ 未通過")
    col3.metric("驗收狀態",    state_label)
    col4.metric("未匹配檔案",  len(imp.get("unmatched_files", [])))

    if not validation.get("ok"):
        st.error("Validation 失敗，請回到 X-AnyLabeling 修正後重新匯入。")
        with st.expander("問題詳細"):
            st.json(validation.get("issues", []))

    if imp.get("unmatched_files"):
        st.warning(f"無法比對到 asset 的檔案：{imp['unmatched_files']}")

    if validation.get("ok") and aset.get("state") == "approved":
        st.success("標注已驗收通過，匯出檔案已產生。")

    st.divider()
    tabs = st.tabs(["匯出內容"] + list(r.get("exports", {}).keys()) + ["Annotation Set"])

    with tabs[0]:
        export_root = Path(r.get("export_root", ""))
        st.markdown(f"Export 根目錄：`{export_root}`")
        for fmt, exp in r.get("exports", {}).items():
            fmt_dir = export_root / fmt.replace("-", "_")
            report  = (exp.get("conversion_report") or {})
            st.markdown(f"**{fmt}** — lossless={report.get('lossless')} "
                        f"warnings={len(report.get('warnings', []))}")
            files = (
                [str(p.relative_to(fmt_dir)) for p in fmt_dir.rglob("*") if p.is_file()]
                if fmt_dir.exists() else []
            )
            st.dataframe([{"file": f} for f in files], use_container_width=True, hide_index=True)

    for i, (fmt, _) in enumerate(r.get("exports", {}).items(), start=1):
        with tabs[i]:
            fmt_dir = Path(r["export_root"]) / fmt.replace("-", "_")
            if fmt == "coco":
                ann = fmt_dir / "annotations.json"
                st.code(ann.read_text(encoding="utf-8") if ann.exists() else "", language="json")
            elif fmt in ("labelme", "x-anylabeling", "isat"):
                files = sorted(p for p in fmt_dir.glob("*.json")
                               if p.name not in {"manifest.json", "conversion_report.json"})
                if files:
                    st.code(files[0].read_text(encoding="utf-8"), language="json")
            elif fmt in ("yolo-detection", "yolo-segmentation"):
                lf = sorted((fmt_dir / "labels").glob("*.txt"))
                if lf:
                    st.code(lf[0].read_text(encoding="utf-8"), language="text")
                cls = fmt_dir / "classes.txt"
                st.code(cls.read_text(encoding="utf-8") if cls.exists() else "", language="text")

    with tabs[-1]:
        st.json(aset)


# ── dispatcher ────────────────────────────────────────────────────────────────

def render_output(result: dict) -> None:
    mode = result.get("mode", "browse")
    if mode in {"xany_phase1", "labeling_phase1"}:
        _render_xany_phase1(result)
    elif mode in {"xany_phase2", "labeling_phase2"}:
        _render_xany_phase2(result)
    else:
        if result.get("error") == "db_not_found":
            st.error(f"找不到資料庫：{result.get('db_path')}")
            return
        _render_browse(result)
