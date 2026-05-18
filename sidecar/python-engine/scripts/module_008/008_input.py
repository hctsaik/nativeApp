from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageOps
from streamlit_autorefresh import st_autorefresh

try:
    from _config import get_annotation_labels
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("_008_process", Path(__file__).resolve().parent / "008_process.py")
    _proc = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_proc)
except ImportError:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _config import get_annotation_labels
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("_008_process", Path(__file__).resolve().parent / "008_process.py")
    _proc = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_proc)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_SESSION_BASE = _PROJECT_ROOT / "tmp" / "cim_log" / "video-tracking"

_CJK_FONTS = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msjh.ttc",
    "C:/Windows/Fonts/mingliu.ttc",
    "C:/Windows/Fonts/simsun.ttc",
]

_PALETTE = [(255, 80, 80), (80, 180, 255), (80, 220, 80), (255, 200, 60), (200, 80, 255)]


def _get_font(size: int):
    for p in _CJK_FONTS:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _session_id(video_path: str) -> str:
    h = hashlib.md5(video_path.encode()).hexdigest()[:8]
    return f"vid_{h}_{int(time.time())}"


def _extract_frame_jpg(video_path: str, frame_idx: int, dest: Path) -> np.ndarray | None:
    if dest.exists():
        return cv2.imread(str(dest))
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dest), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return frame


def _get_video_meta(video_path: str) -> dict | None:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return {"fps": fps, "total_frames": total, "width": w, "height": h, "duration": total / fps}


def _draw_bboxes_on_frame(frame_bgr: np.ndarray, shapes: list[dict]) -> bytes:
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


def _read_anchor_annotation(session_dir: Path) -> list[dict]:
    anchor_dir = session_dir / "anchor_labels"
    if not anchor_dir.exists():
        return []
    for f in anchor_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            shapes = [s for s in data.get("shapes", []) if s.get("shape_type") == "rectangle"]
            if shapes:
                return shapes
        except Exception:
            pass
    return []


def _launch_xany_for_anchor(session_dir: Path, anchor_frame_path: Path, labels: list[str]) -> str | None:
    anchor_labels_dir = session_dir / "anchor_labels"
    anchor_labels_dir.mkdir(parents=True, exist_ok=True)

    classes_txt = session_dir / "classes.txt"
    if labels:
        classes_txt.write_text("\n".join(labels), encoding="utf-8")

    xany_work = session_dir / ".xanylabeling"
    exe = _proc.get_xany_exe(_PROJECT_ROOT)

    cmd = _proc.xany_command_prefix(exe) + [
        "--filename", str(anchor_frame_path),
        "--output", str(anchor_labels_dir),
        "--work-dir", str(xany_work),
        "--nodata", "--autosave", "--no-auto-update-check",
    ]
    if classes_txt.exists():
        cmd += ["--labels", str(classes_txt), "--validatelabel", "exact"]

    try:
        subprocess.Popen(cmd, env=_proc.xany_subprocess_env(exe))
        return None
    except Exception as e:
        return str(e)


@st.fragment(run_every=0.12)
def _anchor_nav_frag(video_path: str, session_dir: Path, fps: float,
                     total_frames: int, labels: list[str]):
    max_frame = max(0, total_frames - 1)

    # Auto-play: advance BEFORE slider renders (run_every drives cadence)
    if st.session_state.get("in_auto_fwd"):
        cur = st.session_state.get("anchor_idx", total_frames // 2)
        if cur < max_frame:
            st.session_state["anchor_idx"] = cur + 1
        else:
            st.session_state["in_auto_fwd"] = False
    elif st.session_state.get("in_auto_rev"):
        cur = st.session_state.get("anchor_idx", total_frames // 2)
        if cur > 0:
            st.session_state["anchor_idx"] = cur - 1
        else:
            st.session_state["in_auto_rev"] = False

    c1, c2, c3, c4, c5, c6 = st.columns([1, 1, 6, 1, 1, 2])
    with c1:
        lbl = "⏹ 停" if st.session_state.get("in_auto_rev") else "⏮ 自動"
        if st.button(lbl, use_container_width=True, key="in_btn_auto_rev"):
            st.session_state["in_auto_fwd"] = False
            st.session_state["in_auto_rev"] = not st.session_state.get("in_auto_rev", False)
    with c2:
        cur_idx = st.session_state.get("anchor_idx", total_frames // 2)
        if st.button("◀", disabled=(cur_idx <= 0), use_container_width=True, key="in_btn_prev"):
            st.session_state["in_auto_fwd"] = False
            st.session_state["in_auto_rev"] = False
            st.session_state["anchor_idx"] = max(0, cur_idx - 1)
    with c3:
        anchor_idx = st.slider(
            "Anchor Frame", min_value=0, max_value=max_frame,
            key="anchor_idx", label_visibility="collapsed",
            help=f"選擇要標注的關鍵幀（{fps:.0f} fps）",
        )
    with c4:
        if st.button("▶", disabled=(anchor_idx >= max_frame), use_container_width=True, key="in_btn_next"):
            st.session_state["in_auto_fwd"] = False
            st.session_state["in_auto_rev"] = False
            st.session_state["anchor_idx"] = min(max_frame, anchor_idx + 1)
    with c5:
        lbl = "⏹ 停" if st.session_state.get("in_auto_fwd") else "⏭ 自動"
        if st.button(lbl, use_container_width=True, key="in_btn_auto_fwd"):
            st.session_state["in_auto_rev"] = False
            st.session_state["in_auto_fwd"] = not st.session_state.get("in_auto_fwd", False)
    with c6:
        xany_placeholder = st.empty()

    anchor_time = anchor_idx / fps
    st.caption(f"幀 **{anchor_idx}**　{anchor_time:.2f}s　（共 {total_frames} 幀）")

    anchor_frame_path = Path(session_dir) / "frames" / f"frame_{anchor_idx:06d}.jpg"
    anchor_frame_path.parent.mkdir(parents=True, exist_ok=True)
    anchor_frame = _extract_frame_jpg(video_path, anchor_idx, anchor_frame_path)

    anchor_shapes = _read_anchor_annotation(Path(session_dir))

    with xany_placeholder:
        if st.button("🖊 X-AnyLabeling 標注", use_container_width=True,
                     type="primary", key="xany_launch_btn"):
            err = _launch_xany_for_anchor(Path(session_dir), anchor_frame_path, labels)
            if err:
                st.error(f"啟動失敗：{err}")
            else:
                st.success("X-AnyLabeling 已啟動")

    if anchor_frame is not None:
        if anchor_shapes:
            ann_bytes = _draw_bboxes_on_frame(anchor_frame, anchor_shapes)
            st.image(ann_bytes, use_container_width=True)
        else:
            st.image(cv2.cvtColor(anchor_frame, cv2.COLOR_BGR2RGB),
                     caption="Anchor 幀預覽（尚未標注）", use_container_width=True)

    if anchor_shapes:
        st.success(f"✅ {len(anchor_shapes)} 個標注框")
        for s in anchor_shapes:
            pts = s.get("points", [])
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            if xs and ys:
                st.caption(f"  {s['label']}：({min(xs):.0f},{min(ys):.0f}) → ({max(xs):.0f},{max(ys):.0f})")
    else:
        st.info("尚未偵測到標注，X-AnyLabeling 存檔後自動更新。")


def render_input() -> dict:
    st.subheader(":material/movie: 影片追蹤標注")
    st.caption(
        "**工作流程：** "
        "① 選擇影片 + anchor 幀　"
        "→ ② 在 X-AnyLabeling 畫框　"
        "→ ③ 設定時間範圍　"
        "→ ④ 點「▶ 執行」開始追蹤傳播"
    )

    with st.expander("📖 使用說明", expanded=False):
        _guide_path = Path(__file__).resolve().parent / "guide.html"
        if _guide_path.exists():
            import streamlit.components.v1 as _components
            _components.html(_guide_path.read_text(encoding="utf-8"), height=800, scrolling=True)

    # ── 步驟 1：影片選擇 ──────────────────────────────────────────────────────
    with st.expander("① 影片與標注設定", expanded=True):
        # Transfer browsed path before widget renders (Streamlit forbids setting widget key after render)
        if "_v_path_chosen" in st.session_state:
            st.session_state["v_path"] = st.session_state.pop("_v_path_chosen")

        path_col, btn_col = st.columns([5, 1])
        with path_col:
            video_path = st.text_input(
                "影片路徑（MP4 / AVI / MOV）",
                key="v_path",
                placeholder="C:/path/to/video.mp4",
            )
        with btn_col:
            st.markdown("<div style='margin-top:28px'>", unsafe_allow_html=True)
            if st.button("📂 瀏覽", use_container_width=True, key="browse_video_btn"):
                try:
                    result = subprocess.run(
                        [sys.executable, "-c",
                         "import tkinter as tk; from tkinter import filedialog; "
                         "root=tk.Tk(); root.withdraw(); root.wm_attributes('-topmost',True); "
                         "p=filedialog.askopenfilename(title='選擇影片檔案',"
                         "filetypes=[('影片檔案','*.mp4 *.avi *.mov *.mkv *.wmv *.flv *.m4v'),('所有檔案','*.*')]); "
                         "root.destroy(); print(p or '',end='')"],
                        capture_output=True, text=True, timeout=60,
                    )
                    chosen = result.stdout.strip()
                    if chosen:
                        st.session_state["_v_path_chosen"] = chosen
                        st.rerun()
                except Exception as e:
                    st.warning(f"無法開啟檔案選擇器：{e}\n請直接在上方文字框貼上路徑。")
            st.markdown("</div>", unsafe_allow_html=True)

        col_labels, col_ws = st.columns([1, 2])
        with col_labels:
            labels = get_annotation_labels()
            st.caption(f"**標注類別**：{', '.join(labels)}")
            st.caption("（在 006 動物影像標記的路徑設定裡可修改）")
        with col_ws:
            session_base = st.text_input("工作區根目錄", value=str(_DEFAULT_SESSION_BASE))

    if not video_path or not Path(video_path).exists():
        if video_path:
            st.error(f"找不到影片：{video_path}")
        return {"mode": "idle", "video_path": "", "anchor_frame_idx": 0}

    # Load video meta (cache in session_state)
    meta_key = f"meta_{video_path}"
    if meta_key not in st.session_state:
        meta = _get_video_meta(video_path)
        if meta is None:
            st.error("無法讀取影片，請確認格式是否支援（MP4/AVI/MOV）。")
            return {"mode": "idle", "video_path": video_path, "anchor_frame_idx": 0}
        st.session_state[meta_key] = meta
    meta = st.session_state[meta_key]

    fps = meta["fps"]
    total_frames = meta["total_frames"]
    duration = meta["duration"]

    st.info(
        f"FPS: {fps:.1f}　|　總幀數: {total_frames}　|　"
        f"時長: {duration:.1f} 秒　|　解析度: {meta['width']}×{meta['height']}"
    )

    # Determine session dir for this video (before fragment so session_dir is ready)
    if "session_dir" not in st.session_state or st.session_state.get("session_video") != video_path:
        sid = _session_id(video_path)
        sd = Path(session_base) / sid
        sd.mkdir(parents=True, exist_ok=True)
        st.session_state["session_dir"] = str(sd)
        st.session_state["session_video"] = video_path

    session_dir = Path(st.session_state["session_dir"])

    # ── 步驟 2 + 3：Anchor 幀選擇 + X-AnyLabeling ────────────────────────────
    st.divider()
    st.markdown("**② 選擇 Anchor 幀　③ 在 X-AnyLabeling 標注**")

    st.markdown("""<style>
    [data-testid="stImage"] img {
        max-height: 62vh;
        object-fit: contain;
        width: 100% !important;
    }
    </style>""", unsafe_allow_html=True)

    # Fragment handles nav + image display; run_every drives auto-play cadence
    _anchor_nav_frag(video_path, session_dir, fps, total_frames, labels)

    # Read state set by fragment for use below
    anchor_idx = st.session_state.get("anchor_idx", total_frames // 2)
    anchor_shapes = _read_anchor_annotation(session_dir)

    # Anchor-poll refresh — only when not auto-playing and annotation pending
    auto_playing = st.session_state.get("in_auto_fwd") or st.session_state.get("in_auto_rev")
    if not auto_playing and not anchor_shapes:
        st_autorefresh(interval=2000, key="anchor_poll")

    # ── 步驟 4：時間範圍設定 ─────────────────────────────────────────────────
    st.divider()
    st.markdown("**④ 設定追蹤時間範圍**")
    r_col1, r_col2 = st.columns(2)
    with r_col1:
        before_sec = st.number_input("往前幾秒", min_value=0.0, max_value=60.0, value=1.0, step=0.5,
                                     key="before_sec")
    with r_col2:
        after_sec = st.number_input("往後幾秒", min_value=0.0, max_value=60.0, value=1.0, step=0.5,
                                    key="after_sec")

    start_frame = max(0, anchor_idx - int(before_sec * fps))
    end_frame = min(total_frames - 1, anchor_idx + int(after_sec * fps))
    n_frames = end_frame - start_frame + 1
    st.caption(f"追蹤範圍：幀 {start_frame} → {end_frame}（共 **{n_frames}** 幀 / {n_frames/fps:.1f} 秒）")

    # Convert anchor shapes to anchor_bboxes for execute_logic
    anchor_bboxes = []
    for s in anchor_shapes:
        pts = s.get("points", [])
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        if xs and ys:
            anchor_bboxes.append({
                "label": s["label"],
                "x1": float(min(xs)),
                "y1": float(min(ys)),
                "x2": float(max(xs)),
                "y2": float(max(ys)),
            })

    st.divider()
    if anchor_bboxes:
        st.success(f"✅ 已偵測到 {len(anchor_bboxes)} 個標注框，點選上方「▶ 執行」開始追蹤傳播。")
    else:
        st.warning("請先在 X-AnyLabeling 畫好 bbox 後，再點選上方「▶ 執行」。")

    return {
        "mode": "tracking",
        "video_path": str(video_path),
        "anchor_frame_idx": anchor_idx,
        "session_dir": str(session_dir),
        "before_sec": before_sec,
        "after_sec": after_sec,
        "anchor_bboxes": anchor_bboxes,
        "meta": meta,
        "labels": labels,
    }
