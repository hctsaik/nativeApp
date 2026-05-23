from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent
_PROCESS_FILE = _HERE / "018_process.py"

_THUMB_SIZE = (320, 240)
_BOX_COLORS = [
    "#FF4444", "#44AA44", "#4488FF", "#FF8800", "#AA44AA",
    "#00AAAA", "#FFAA00", "#8844FF", "#FF44AA", "#44FF88",
]

# Cache: {(file_path, ann_mtime): PIL.Image}
_overlay_cache: dict = {}


def _load_process_mod():
    spec = importlib.util.spec_from_file_location("_018_process", _PROCESS_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _render_thumb_with_overlay(file_path: str, ann_path: str, show_overlay: bool) -> bytes | None:
    """Return JPEG bytes of thumbnail, optionally with BBox overlay drawn."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None

    img_path = Path(file_path)
    if not img_path.exists():
        return None

    cache_key = (file_path, ann_path, show_overlay)
    if show_overlay:
        ann_p = Path(ann_path)
        ann_mtime = ann_p.stat().st_mtime if ann_p.exists() else 0
        cache_key = (file_path, ann_path, ann_mtime)

    if cache_key in _overlay_cache:
        return _overlay_cache[cache_key]

    try:
        img = Image.open(img_path).convert("RGB")
        orig_w, orig_h = img.size
        img.thumbnail(_THUMB_SIZE, Image.LANCZOS)
        thumb_w, thumb_h = img.size
        scale_x = thumb_w / orig_w
        scale_y = thumb_h / orig_h

        if show_overlay and ann_path:
            ann_p = Path(ann_path)
            if ann_p.exists():
                try:
                    ann_data = json.loads(ann_p.read_text(encoding="utf-8"))
                    shapes = ann_data.get("shapes", [])
                    draw = ImageDraw.Draw(img, "RGBA")
                    label_color_map: dict[str, str] = {}
                    color_idx = 0

                    for shape in shapes:
                        label = shape.get("label", "")
                        pts = shape.get("points", [])
                        if not pts:
                            continue

                        if label not in label_color_map:
                            label_color_map[label] = _BOX_COLORS[color_idx % len(_BOX_COLORS)]
                            color_idx += 1
                        color_hex = label_color_map[label]
                        r, g, b = _hex_to_rgb(color_hex)

                        xs = [p[0] * scale_x for p in pts]
                        ys = [p[1] * scale_y for p in pts]
                        x0, y0 = min(xs), min(ys)
                        x1, y1 = max(xs), max(ys)

                        draw.rectangle([x0, y0, x1, y1], outline=(r, g, b, 255), width=2)
                        draw.rectangle([x0, y0, x0 + len(label) * 6 + 4, y0 + 14],
                                       fill=(r, g, b, 200))
                        try:
                            draw.text((x0 + 2, y0 + 1), label, fill=(255, 255, 255, 255))
                        except Exception:
                            pass
                except Exception:
                    pass

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        result = buf.getvalue()
        _overlay_cache[cache_key] = result
        if len(_overlay_cache) > 500:
            oldest = next(iter(_overlay_cache))
            del _overlay_cache[oldest]
        return result
    except Exception:
        return None


def _get_items(result: dict) -> list[dict]:
    """Return cached items or refresh from process module."""
    mid = result.get("manifest_id", "")
    cached = st.session_state.get("m018_items_cache")
    if (
        cached is not None
        and st.session_state.get("m018_cache_mid") == mid
        and st.session_state.get("m018_cache_filter") == result.get("filter")
        and st.session_state.get("m018_cache_label") == result.get("label_filter")
    ):
        return cached

    mod = _load_process_mod()
    fresh = mod.execute_logic({
        "manifest_id": mid,
        "filter": result.get("filter", "全部"),
        "label_filter": result.get("label_filter", ""),
    })
    items = fresh.get("items", [])
    st.session_state["m018_items_cache"] = items
    st.session_state["m018_cache_mid"] = mid
    st.session_state["m018_cache_filter"] = result.get("filter")
    st.session_state["m018_cache_label"] = result.get("label_filter")
    return items


PAGE_SIZE = 30


def render_output(result: dict) -> None:
    if not result or result.get("error"):
        st.info("請先在 Input 頁籤確認設定，然後按下 ▶ 執行。")
        if result and result.get("error"):
            st.error(result["error"])
        return

    manifest_id = result.get("manifest_id", "")
    if not manifest_id:
        st.warning("未選擇 Manifest。")
        return

    items = _get_items(result)
    cols_count: int = result.get("cols_count", 3)
    show_overlay: bool = result.get("show_overlay", True)

    # ── 摘要 ─────────────────────────────────────────────────────────────────
    st.subheader("🖼️ Review Gallery")
    total_raw = result.get("total_raw", len(items))
    m1, m2, m3 = st.columns(3)
    m1.metric("顯示", len(items))
    m2.metric("總計", total_raw)
    has_bbox = sum(1 for it in items if it["has_bbox"])
    m3.metric("含 BBox", has_bbox)

    if not items:
        st.info("沒有符合篩選條件的圖片。")
        return

    # ── 分頁 ─────────────────────────────────────────────────────────────────
    n_pages = max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = st.session_state.get("m018_page", 0)
    if page >= n_pages:
        page = 0
        st.session_state["m018_page"] = 0

    if n_pages > 1:
        pg_cols = st.columns([1, 3, 1])
        if pg_cols[0].button("◀ 上頁", disabled=page == 0, key="m018_prev"):
            st.session_state["m018_page"] = page - 1
            st.rerun()
        pg_cols[1].caption(f"第 {page + 1} / {n_pages} 頁")
        if pg_cols[2].button("下頁 ▶", disabled=page == n_pages - 1, key="m018_next"):
            st.session_state["m018_page"] = page + 1
            st.rerun()

    page_items = items[page * PAGE_SIZE: (page + 1) * PAGE_SIZE]

    # ── Detail view ──────────────────────────────────────────────────────────
    sel_id = st.session_state.get("m018_selected")
    if sel_id:
        sel_item = next((it for it in items if it["item_id"] == sel_id), None)
        if sel_item:
            st.divider()
            st.markdown(f"**詳細檢視** — `{Path(sel_item['file_path']).name}`")
            d1, d2 = st.columns([2, 1])
            with d1:
                img_bytes = _render_thumb_with_overlay(
                    sel_item["file_path"], sel_item["ann_path"], show_overlay
                )
                if img_bytes:
                    st.image(img_bytes, use_container_width=True)
                else:
                    st.warning("無法載入圖片")
            with d2:
                st.markdown(f"**BBox 數量**：{sel_item['shape_count']}")
                st.markdown(f"**標籤**：{', '.join(sel_item['labels']) or '（無）'}")
                st.markdown(f"**分類**：{sel_item['classification'] or '（無）'}")
                st.markdown(f"**路徑**：`{sel_item['file_path']}`")
            if st.button("✕ 關閉詳細檢視", key="m018_close_detail"):
                st.session_state.pop("m018_selected", None)
                st.rerun()
            st.divider()

    # ── Grid ─────────────────────────────────────────────────────────────────
    for row_start in range(0, len(page_items), cols_count):
        row_items = page_items[row_start: row_start + cols_count]
        cols = st.columns(cols_count)
        for col, it in zip(cols, row_items):
            with col:
                img_bytes = _render_thumb_with_overlay(
                    it["file_path"], it["ann_path"], show_overlay
                )
                fname = Path(it["file_path"]).name if it["file_path"] else "?"
                if img_bytes:
                    st.image(img_bytes, use_container_width=True)
                else:
                    st.markdown(f"🖼️ `{fname}`\n\n*(無法載入)*")

                badge = ""
                if it["has_bbox"]:
                    badge += f"🟢 {it['shape_count']}個BBox　"
                else:
                    badge += "⬜ 未標注　"
                if it["has_classification"]:
                    badge += f"🏷️ {it['classification']}"

                st.caption(badge or fname)
                if st.button("🔍 詳細", key=f"m018_detail_{it['item_id']}"):
                    st.session_state["m018_selected"] = it["item_id"]
                    st.rerun()

    # ── 重新整理 ─────────────────────────────────────────────────────────────
    st.divider()
    if st.button("🔄 重新整理", key="m018_refresh"):
        st.session_state.pop("m018_items_cache", None)
        st.rerun()
