from __future__ import annotations

import io
import json
import os
from pathlib import Path

import cv2
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from streamlit_autorefresh import st_autorefresh

try:
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("_008_process", Path(__file__).resolve().parent / "008_process.py")
    _proc = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_proc)
except Exception:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("_008_process", Path(__file__).resolve().parent / "008_process.py")
    _proc = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_proc)

_PROJECT_ROOT = Path(__file__).resolve().parents[6]
_DEFAULT_SESSION_BASE = _PROJECT_ROOT / "tmp" / "cim_log" / "video-tracking"

_CJK_FONTS = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msjh.ttc",
    "C:/Windows/Fonts/mingliu.ttc",
    "C:/Windows/Fonts/simsun.ttc",
]
_PALETTE = [(255, 80, 80), (80, 180, 255), (80, 220, 80), (255, 200, 60), (200, 80, 255)]

_IMG_CSS = """<style>
[data-testid="stImage"] img {
    max-height: 62vh;
    object-fit: contain;
    width: 100% !important;
}
</style>"""


def _get_font(size: int):
    for p in _CJK_FONTS:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _confidence_from_shapes(shapes: list[dict]) -> float:
    confs = []
    for s in shapes:
        desc = s.get("description", "")
        if "confidence=" in desc:
            try:
                confs.append(float(desc.split("confidence=")[1].split()[0]))
            except (IndexError, ValueError):
                pass
    return sum(confs) / len(confs) if confs else 1.0


def _conf_badge(conf: float) -> str:
    if conf >= 0.7:
        return "🟢"
    if conf >= 0.4:
        return "🟡"
    return "🔴"


def _draw_bboxes(frame_bgr, shapes: list[dict]) -> bytes:
    img = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img)
    fs = max(14, img.height // 30)
    font = _get_font(fs)
    colour_map: dict[str, tuple] = {}
    for shape in shapes:
        label = shape.get("label", "?")
        pts = shape.get("points", [])
        if not pts:
            continue
        if label not in colour_map:
            colour_map[label] = _PALETTE[len(colour_map) % len(_PALETTE)]
        c = colour_map[label]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        draw.rectangle([x0, y0, x1, y1], outline=c, width=3)
        lw = sum(fs for ch in label if ord(ch) > 127) + sum(int(fs * 0.6) for ch in label if ord(ch) <= 127) + 8
        draw.rectangle([x0, y0 - fs - 4, x0 + lw, y0], fill=c)
        draw.text((x0 + 4, y0 - fs - 2), label, fill=(255, 255, 255), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _read_frame(session_dir: Path, frame_idx: int):
    p = session_dir / "frames" / f"frame_{frame_idx:06d}.jpg"
    if p.exists():
        return cv2.imread(str(p))
    return None


def _render_progress(task: dict, session_dir: Path):
    state = task.get("state", "idle")
    progress = task.get("progress", 0.0)
    current = task.get("current_frame", 0)
    total = task.get("total_frames", 0)

    if not task.get("dino_available", True):
        st.warning("⚠️ DINOv2 未安裝 — 使用 Optical Flow 單一追蹤模式。")

    if state == "running":
        st.info(f"⏳ 追蹤中… {current}/{total} 幀")
        st.progress(progress)
        st_autorefresh(interval=1500, key="tracking_poll")
    elif state == "error":
        st.error(f"❌ 追蹤失敗：{task.get('error', '未知錯誤')}")
    elif state == "done":
        st.success(f"✅ 追蹤完成，共處理 {total} 幀")
    else:
        st.info("尚未開始追蹤，請在 Input 頁面設定並啟動。")


@st.fragment(run_every=0.12)
def _frame_browser_frag(session_dir: Path, frame_indices: list[int], session: dict):
    anchor_idx = session.get("anchor_frame_idx", -1)
    fps = session.get("fps", 30.0)
    total = len(frame_indices)

    if "out_pos" not in st.session_state:
        default = anchor_idx if anchor_idx in frame_indices else frame_indices[0]
        st.session_state["out_pos"] = frame_indices.index(default)
    cur_pos = int(st.session_state["out_pos"])
    cur_pos = max(0, min(cur_pos, total - 1))

    # Auto-play: advance BEFORE slider renders (run_every drives the cadence)
    if st.session_state.get("out_auto_fwd"):
        if cur_pos < total - 1:
            cur_pos += 1
        else:
            st.session_state["out_auto_fwd"] = False
    elif st.session_state.get("out_auto_rev"):
        if cur_pos > 0:
            cur_pos -= 1
        else:
            st.session_state["out_auto_rev"] = False

    st.session_state["out_slider"] = cur_pos

    c1, c2, c3, c4, c5 = st.columns([1, 1, 6, 1, 1])
    with c1:
        lbl = "⏹ 停" if st.session_state.get("out_auto_rev") else "⏮ 自動"
        if st.button(lbl, use_container_width=True, key="out_btn_auto_rev"):
            st.session_state["out_auto_fwd"] = False
            st.session_state["out_auto_rev"] = not st.session_state.get("out_auto_rev", False)
            st.session_state["out_pos"] = cur_pos
    with c2:
        if st.button("◀", disabled=(cur_pos == 0), use_container_width=True, key="out_btn_prev"):
            st.session_state["out_auto_fwd"] = False
            st.session_state["out_auto_rev"] = False
            st.session_state["out_pos"] = cur_pos - 1
    with c3:
        slider_pos = st.slider(
            "幀位置", min_value=0, max_value=total - 1,
            key="out_slider", label_visibility="collapsed",
        )
        if slider_pos != cur_pos:
            st.session_state["out_auto_fwd"] = False
            st.session_state["out_auto_rev"] = False
            st.session_state["out_pos"] = slider_pos
            cur_pos = slider_pos
    with c4:
        if st.button("▶", disabled=(cur_pos == total - 1), use_container_width=True, key="out_btn_next"):
            st.session_state["out_auto_fwd"] = False
            st.session_state["out_auto_rev"] = False
            st.session_state["out_pos"] = cur_pos + 1
    with c5:
        lbl = "⏹ 停" if st.session_state.get("out_auto_fwd") else "⏭ 自動"
        if st.button(lbl, use_container_width=True, key="out_btn_auto_fwd"):
            st.session_state["out_auto_rev"] = False
            st.session_state["out_auto_fwd"] = not st.session_state.get("out_auto_fwd", False)
            st.session_state["out_pos"] = cur_pos

    st.session_state["out_pos"] = cur_pos
    fidx = frame_indices[cur_pos]

    ann = _proc.load_annotation(session_dir, fidx)
    shapes = ann.get("shapes", []) if ann else []
    conf = _confidence_from_shapes(shapes)
    is_anchor = (fidx == anchor_idx)
    st.caption(
        f"幀 **{fidx}**　{fidx/fps:.2f}s　{_conf_badge(conf)} {conf:.2f}"
        + (" ★ Anchor" if is_anchor else "")
        + f"　（{cur_pos + 1} / {total}）"
    )

    frame_bgr = _read_frame(session_dir, fidx)
    if frame_bgr is not None:
        img_bytes = _draw_bboxes(frame_bgr, shapes) if shapes else None
        if img_bytes:
            st.image(img_bytes, use_container_width=True)
        else:
            st.image(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB),
                     caption="此幀無追蹤結果", use_container_width=True)
    else:
        st.warning(f"找不到幀圖片：frame_{fidx:06d}.jpg")


def _render_frame_browser(session_dir: Path, frame_indices: list[int], session: dict):
    st.markdown(_IMG_CSS, unsafe_allow_html=True)
    _frame_browser_frag(session_dir, frame_indices, session)

    # Correction panel — outside the fragment so it doesn't flicker during auto-play
    labels = session.get("labels", [])
    cur_pos = st.session_state.get("out_pos", 0)
    cur_pos = max(0, min(cur_pos, len(frame_indices) - 1))
    fidx = frame_indices[cur_pos]
    ann = _proc.load_annotation(session_dir, fidx)
    shapes = ann.get("shapes", []) if ann else []

    with st.expander("✏️ 手動校正此幀", expanded=False):
        if st.session_state.get("correction_frame") != fidx:
            default_bboxes = []
            for s in shapes:
                pts = s.get("points", [])
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                if xs and ys:
                    default_bboxes.append({
                        "label": s.get("label", labels[0] if labels else ""),
                        "x1": float(min(xs)), "y1": float(min(ys)),
                        "x2": float(max(xs)), "y2": float(max(ys)),
                    })
            st.session_state["correction_bboxes"] = default_bboxes
            st.session_state["correction_frame"] = fidx

        correction_bboxes = st.session_state.get("correction_bboxes", [])
        label_opts = labels if labels else [""]
        n_boxes = int(st.number_input("物件數量", min_value=0, max_value=10,
                                      value=len(correction_bboxes), step=1,
                                      key=f"n_boxes_{fidx}"))
        while len(correction_bboxes) < n_boxes:
            correction_bboxes.append({"label": label_opts[0], "x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 100.0})
        while len(correction_bboxes) > n_boxes:
            correction_bboxes.pop()

        updated = []
        for i, bbox in enumerate(correction_bboxes):
            bc1, bc2, bc3, bc4, bc5 = st.columns([2, 1, 1, 1, 1])
            with bc1:
                lbl = st.selectbox(f"Label #{i+1}", label_opts,
                                   index=label_opts.index(bbox["label"]) if bbox["label"] in label_opts else 0,
                                   key=f"bl_{fidx}_{i}")
            with bc2:
                x1 = st.number_input("x1", value=bbox["x1"], step=1.0, key=f"bx1_{fidx}_{i}", label_visibility="collapsed")
            with bc3:
                y1 = st.number_input("y1", value=bbox["y1"], step=1.0, key=f"by1_{fidx}_{i}", label_visibility="collapsed")
            with bc4:
                x2 = st.number_input("x2", value=bbox["x2"], step=1.0, key=f"bx2_{fidx}_{i}", label_visibility="collapsed")
            with bc5:
                y2 = st.number_input("y2", value=bbox["y2"], step=1.0, key=f"by2_{fidx}_{i}", label_visibility="collapsed")
            updated.append({"label": lbl, "x1": float(x1), "y1": float(y1), "x2": float(x2), "y2": float(y2)})
        st.session_state["correction_bboxes"] = updated

        a1, a2 = st.columns(2)
        with a1:
            if st.button("✅ 確認校正", type="primary", use_container_width=True, key=f"save_{fidx}"):
                _proc.save_correction(session_dir, fidx, updated)
                st.toast(f"幀 {fidx} 校正已儲存", icon="✅")
                st.rerun()
        with a2:
            if st.button("🔄 從此幀重新傳播", use_container_width=True, key=f"reprop_{fidx}"):
                _proc.save_correction(session_dir, fidx, updated)
                _proc.re_propagate(session_dir, fidx)
                st.success(f"已從幀 {fidx} 重新追蹤")
                st.session_state.pop("correction_bboxes", None)
                st.rerun()


def render_output(result: dict) -> None:
    if result.get("mode") == "idle":
        st.info("請先在 Input 頁面選擇影片並啟動追蹤。")
        return

    session_dir_str = result.get("session_dir", "")
    if not session_dir_str:
        base = _DEFAULT_SESSION_BASE
        if base.exists():
            for s in sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                if (s / "session.json").exists():
                    session_dir_str = str(s)
                    break

    if not session_dir_str:
        st.info("找不到追蹤工作階段，請先在 Input 頁面啟動追蹤。")
        return

    session_dir = Path(session_dir_str)
    session = _proc.load_session(session_dir)
    if not session:
        st.info("找不到 session.json，請在 Input 頁面啟動追蹤。")
        return

    task = _proc.get_task_status(session_dir)
    _render_progress(task, session_dir)

    frame_indices = _proc.list_annotated_frames(session_dir)
    if not frame_indices:
        if task.get("state") != "running":
            st.warning("尚未有追蹤結果，請啟動傳播後等待完成。")
        return

    st.divider()
    _render_frame_browser(session_dir, frame_indices, session)

    st.divider()
    exp_col, info_col = st.columns([1, 3])
    with exp_col:
        export_format = st.selectbox("匯出格式", ["x-anylabeling", "labelme", "isat"], index=0)
        if st.button("📤 匯出標注 JSON", type="primary", use_container_width=True,
                     disabled=task.get("state") == "running"):
            r = _proc.export_annotation_format(session_dir, export_format)
            st.success(f"✅ 匯出完成：{r['annotation_count']} 個 JSON\n\n路徑：`{r['export_dir']}`")
    with info_col:
        st.caption(f"工作區：`{session_dir}`　已追蹤幀數：{len(frame_indices)}")
