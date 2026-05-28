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
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stderr,
)
_log = logging.getLogger("m012_output")

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

# ─── AI Pre-label helpers ─────────────────────────────────────────────────────

_AI_CFG_SPEC = _ilu.spec_from_file_location(
    "_016_config", _HERE.parent / "module_016" / "_config.py"
)
_ai_cfg = _ilu.module_from_spec(_AI_CFG_SPEC)
_AI_CFG_SPEC.loader.exec_module(_ai_cfg)

_help_spec = _ilu.spec_from_file_location("_help", _HERE.parent / "shared" / "_help.py")
_help = _ilu.module_from_spec(_help_spec)
_help_spec.loader.exec_module(_help)

# 016_process 是 lazy-loaded，只在按鈕按下時才 import，避免每次 rerun 重載


@st.cache_resource(
    show_spinner="🤖 載入 YOLO 模型中…首次約需 10–30 秒，之後即時生效。請稍候。"
)
def _get_yolo_model(model_path: str):
    """Cache YOLO model by path — loads once per session."""
    from ultralytics import YOLO
    return YOLO(model_path)


def _run_ai_items(items: list[dict], model_path: str, model_type: str,
                  conf: float, overwrite: bool,
                  progress_placeholder=None) -> dict:
    """Run YOLO on given items inline. YOLO model is cached after first load."""
    total = len(items)
    ok = skipped = errors = detected = 0
    model_class_names: list[str] = []

    if model_type == "yolo":
        try:
            if progress_placeholder is not None:
                progress_placeholder.progress(0.0, text="🤖 載入 YOLO 模型中…首次約需 10–30 秒，請稍候。")
            model = _get_yolo_model(model_path)
            model_class_names = list(model.names.values()) if hasattr(model, "names") else []
        except Exception as exc:
            return {"ok": 0, "skipped": 0, "errors": total, "detected": 0,
                    "error_detail": f"模型載入失敗：{exc}"}

        for it in items:
            fp = it.get("file_path", "")
            if not fp or not Path(fp).exists():
                errors += 1
            else:
                ann_path = Path(fp).with_suffix(".json")
                if ann_path.exists() and not overwrite:
                    skipped += 1
                else:
                    try:
                        results = model(fp, conf=conf, verbose=False)
                        r = results[0]
                        img_w, img_h = int(r.orig_shape[1]), int(r.orig_shape[0])
                        shapes = []
                        for box in r.boxes:
                            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
                            cls_id = int(box.cls[0])
                            label = model.names.get(cls_id, str(cls_id))
                            shapes.append({
                                "label": label,
                                "score": round(float(box.conf[0]), 4),
                                "points": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
                                "group_id": None, "description": "",
                                "difficult": False, "shape_type": "rectangle", "flags": {},
                            })
                        detected += len(shapes)
                        ann_data = {
                            "version": "1.0.0", "flags": {}, "shapes": shapes,
                            "imagePath": Path(fp).name, "imageData": None,
                            "imageHeight": img_h, "imageWidth": img_w,
                        }
                        ann_path.write_text(
                            json.dumps(ann_data, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        ok += 1
                    except Exception:
                        errors += 1

            if progress_placeholder is not None:
                done = ok + skipped + errors
                ratio = done / total if total > 0 else 0
                progress_placeholder.progress(
                    ratio,
                    text=f"{done}/{total}　✅{ok}　⏭️{skipped}　❌{errors}　— {Path(fp).name if fp else '?'}",
                )
    else:
        return {"ok": 0, "skipped": 0, "errors": 0, "detected": 0,
                "error_detail": "Classifier 模式請至 AI Pre-labeling 頁執行"}

    return {"ok": ok, "skipped": skipped, "errors": errors,
            "detected": detected, "model_class_names": model_class_names}


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
        ann_mtime = 0.0
        if ann_path:
            try:
                ann_mtime = Path(ann_path).stat().st_mtime
            except Exception:
                ann_mtime = 0.0
            mtimes[ann_path] = ann_mtime
        items.append({**it, "has_ann": has_ann, "ann_path": ann_path, "shape_count": shape_count, "ann_mtime": ann_mtime})
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
                        new_mtime = Path(new_ap).stat().st_mtime
                    except Exception:
                        new_mtime = 0.0
                    new_mtimes[new_ap] = new_mtime
                    item["ann_mtime"] = new_mtime
                else:
                    item["ann_mtime"] = 0.0
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
                        new_mtime = Path(new_ap).stat().st_mtime
                    except Exception:
                        new_mtime = 0.0
                    new_mtimes[new_ap] = new_mtime
                    item["ann_mtime"] = new_mtime
                else:
                    item["ann_mtime"] = 0.0
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
                 xany_work_dir: str, xany_exe: str, ann_path: str = "",
                 folder_mode: bool = False) -> tuple[str | None, object | None]:
    """以 X-AnyLabeling 開啟圖片或資料夾（非阻塞）。回傳 (error, proc)。

    folder_mode=True 時 file_path 應為資料夾路徑，output 指向同一資料夾。
    """
    classes_txt = Path(classes_path) if classes_path else Path()
    if folder_mode:
        out_dir = Path(file_path)
    else:
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
        proc = subprocess.Popen(cmd)
        return None, proc
    except Exception as e:
        if "4551" in str(e) or "policy" in str(e).lower() or "blocked" in str(e).lower():
            return (
                f"{e}\n\n"
                "【解決方法】請用已信任的 Python 重建 .venv-xanylabeling，例如：\n"
                "  python -m uv venv --python 3.11 --clear .venv-xanylabeling\n"
                "  python -m uv pip install --python .venv-xanylabeling\\Scripts\\python.exe --pre \"x-anylabeling-cvhub[cpu]\"\n"
                "重建後重啟應用程式即可自動使用 py -3.11 啟動。",
                None,
            )
        return str(e), None


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


def _launch_isat(file_path: str, isat_exe: str) -> str | None:
    """Launch ISAT. Current ISAT-SAM console script opens the GUI without file args."""
    import time
    cmd = [isat_exe]
    exe_path = Path(isat_exe)
    if isat_exe != "isat-sam" and exe_path.suffix.lower() == ".py":
        cmd = [sys.executable, str(exe_path)]
    _log.info("[012] _launch_isat cmd=%s cwd=%s", cmd, str(Path(file_path).parent))
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(Path(file_path).parent),
            stderr=subprocess.PIPE,
        )
        time.sleep(1.5)
        ret = proc.poll()
        if ret is not None:
            stderr_out = (proc.stderr.read() or b"").decode("utf-8", errors="replace").strip()
            _log.error("[012] _launch_isat exited immediately ret=%s stderr=%s", ret, stderr_out)
            short = stderr_out[-300:] if len(stderr_out) > 300 else stderr_out
            return f"ISAT 啟動後立即結束（exit={ret}）。\n{short}"
        _log.info("[012] _launch_isat launched pid=%s", proc.pid)
        return None
    except Exception as e:
        _log.error("[012] _launch_isat failed: %s", e)
        return str(e)


def _launch_tool(tool_id: str, file_path: str, exe_override: str | None = None) -> str | None:
    """Unified tool launch via ToolRegistry. Returns error string or None on success."""
    try:
        from annotation.tools.registry import get_tool_registry
        _, adapter = get_tool_registry().get(tool_id)
        return adapter.launch_file(file_path, {"executable_override": exe_override})
    except Exception as exc:
        _log.error("[012] _launch_tool failed tool=%s: %s", tool_id, exc)
        return str(exc)


def _launch_annotation_tool(
    annotation_tool: str,
    file_path: str,
    labels: list[str],
    classes_path: str,
    xany_work_dir: str,
    xany_exe: str,
    labelme_exe: str,
    isat_exe: str = "isat-sam",
    ann_path: str = "",
) -> tuple[str, str | None]:
    """Launch selected annotation tool. Returns (display_name, error)."""
    _log.info("[012] _launch_annotation_tool tool=%s isat_exe=%s file=%s",
              annotation_tool, isat_exe, file_path)
    if annotation_tool == "labelme":
        return "LabelMe", _launch_labelme(file_path, classes_path, labelme_exe)
    if annotation_tool == "isat":
        return "ISAT", _launch_isat(file_path, isat_exe)
    err, _proc = _launch_xany(
        file_path, labels, classes_path, xany_work_dir, xany_exe, ann_path=ann_path
    )
    return "X-AnyLabeling", err


def _proc_alive(proc) -> bool:
    """subprocess 是否仍在執行中。"""
    if proc is None:
        return False
    try:
        return proc.poll() is None
    except Exception:
        return False


def _relaunch_xany_at(
    fp: str,
    labels: list[str],
    classes_path: str,
    xany_work_dir: str,
    xany_exe: str,
) -> None:
    """資料夾模式下切換到指定影像：先 terminate 舊 proc，再啟動新 proc 並更新 session_state。

    成功時：session_state["m012_folder_proc"] = 新 proc；m012_launch_ok 設文字提示。
    失敗時：session_state["m012_folder_proc"] = None；m012_launch_error 設錯誤訊息。
    """
    with st.spinner(f"🚀 X-AnyLabeling 切換至 {Path(fp).name} 中…約需 3-5 秒"):
        _old = st.session_state.get("m012_folder_proc")
        if _proc_alive(_old):
            try:
                _old.terminate()
            except Exception:
                pass
        _err, _new = _launch_xany(fp, labels, classes_path, xany_work_dir, xany_exe)
    if _err:
        st.session_state["m012_launch_error"] = _err
        st.session_state["m012_folder_proc"] = None
    else:
        st.session_state["m012_folder_proc"] = _new
        st.session_state["m012_launch_ok"] = f"🚀 X-AnyLabeling 重新啟動中（切換至 {Path(fp).name}，視窗約 3-5 秒後出現）"


# ─── 強化圖批次標注：產生 / 同步 helpers ─────────────────────────────────────

def _enhance_image_file(src: Path, dst: Path) -> None:
    """讀原圖 → contrast/color 強化 → 寫 dst（JPEG，與 _draw_annotations(enhance=True) 同 factor）。"""
    from PIL import Image, ImageEnhance, ImageOps
    img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    img = ImageEnhance.Contrast(img).enhance(2.2)
    img = ImageEnhance.Color(img).enhance(1.8)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, format="JPEG", quality=92)


def _generate_enhanced_batch(
    items: list[dict],
    enhanced_dir: Path,
    progress_placeholder=None,
) -> dict:
    """批次產生強化圖到 enhanced_dir。回傳 {ok, skipped, errors}。

    已存在且 mtime 比原圖新的會跳過，避免重複工作。
    """
    ok = skipped = errors = 0
    total = len(items)
    for i, it in enumerate(items):
        fp = it.get("file_path", "")
        if not fp:
            errors += 1
            continue
        src = Path(fp)
        if not src.exists():
            errors += 1
            continue
        dst = enhanced_dir / src.name
        if dst.exists():
            try:
                if dst.stat().st_mtime >= src.stat().st_mtime:
                    skipped += 1
                    if progress_placeholder is not None and (i % 20 == 0 or i == total - 1):
                        progress_placeholder.progress(
                            (i + 1) / total,
                            text=f"產生強化圖中…{i + 1}/{total}",
                        )
                    continue
            except Exception:
                pass
        try:
            _enhance_image_file(src, dst)
            ok += 1
        except Exception as e:
            _log.error("[012] _enhance_image_file failed src=%s dst=%s: %s", src, dst, e)
            errors += 1
        if progress_placeholder is not None and (i % 5 == 0 or i == total - 1):
            progress_placeholder.progress(
                (i + 1) / total,
                text=f"產生強化圖中…{i + 1}/{total}",
            )
    return {"ok": ok, "skipped": skipped, "errors": errors}


def _enhanced_to_original_map(items: list[dict], enhanced_dir: Path) -> dict[str, str]:
    """{enhanced JSON path → original image path}，用於 sync 時改寫。"""
    out: dict[str, str] = {}
    for it in items:
        fp = it.get("file_path", "")
        if not fp:
            continue
        src = Path(fp)
        enh_json = enhanced_dir / (src.stem + ".json")
        out[str(enh_json)] = fp
    return out


def _sync_enhanced_annotations(items: list[dict], enhanced_dir: Path) -> int:
    """將 enhanced_dir 內的 .json 標注同步回原圖目錄（改寫 imagePath、保持 mtime 新者）。

    回傳同步的檔案數。
    """
    synced = 0
    if not enhanced_dir.exists():
        return 0
    for it in items:
        fp = it.get("file_path", "")
        if not fp:
            continue
        src = Path(fp)
        enh_json = enhanced_dir / (src.stem + ".json")
        if not enh_json.exists():
            continue
        orig_json = src.with_suffix(".json")
        try:
            enh_mtime = enh_json.stat().st_mtime
            if orig_json.exists() and orig_json.stat().st_mtime >= enh_mtime:
                continue
            data = json.loads(enh_json.read_text(encoding="utf-8"))
            data["imagePath"] = src.name
            orig_json.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            # 同步 mtime 確保 orig >= enh，下次 autorefresh 不重複 sync
            os.utime(orig_json, (enh_mtime, enh_mtime))
            synced += 1
        except Exception as e:
            _log.error("[012] _sync_enhanced_annotations failed %s → %s: %s", enh_json, orig_json, e)
    return synced


def _enhanced_progress(items: list[dict], enhanced_dir: Path) -> tuple[int, int]:
    """回傳 (已存在強化圖數量, 總數)。"""
    if not enhanced_dir.exists():
        return 0, len(items)
    done = sum(1 for it in items if (enhanced_dir / Path(it.get("file_path", "")).name).exists() and it.get("file_path"))
    return done, len(items)


def _launch_xany_folder(
    items: list[dict],
    labels: list[str],
    classes_path: str,
    xany_work_dir: str,
    xany_exe: str,
    folder_override: str | None = None,
) -> tuple[str | None, object | None]:
    """以資料夾模式開啟 X-AnyLabeling。回傳 (error, proc)。

    folder_override 非 None 時直接用該資料夾（用於強化圖模式）；否則自動找出
    包含最多 Manifest 影像的父目錄。
    """
    if not items:
        return "無影像資料", None

    if folder_override:
        folder_path = Path(folder_override)
        if not folder_path.exists():
            return f"強化圖資料夾不存在：{folder_path}", None
    else:
        from collections import Counter
        paths = [Path(it.get("file_path", "")) for it in items if it.get("file_path")]
        if not paths:
            return "無有效影像路徑", None
        dir_counts = Counter(p.parent for p in paths)
        folder_path = dir_counts.most_common(1)[0][0]

    _log.info("[012] _launch_xany_folder folder=%s items=%d enhanced=%s",
              folder_path, len(items), bool(folder_override))
    return _launch_xany(
        str(folder_path), labels, classes_path, xany_work_dir, xany_exe,
        folder_mode=True,
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
    """右欄單張圖片顯示：支援 enhance 對比 + 點擊放大（m012-zoomable）。"""
    if enhance:
        try:
            img_bytes = _draw_annotations(fp, {}, enhance=True)
            st.markdown(_zoomable_img_html(img_bytes, "png"), unsafe_allow_html=True)
            return
        except Exception:
            pass
    full = _make_full_jpeg(fp)
    if full:
        st.markdown(_zoomable_img_html(full, "jpeg"), unsafe_allow_html=True)
    else:
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


@st.cache_data(show_spinner=False, max_entries=200)
def _cached_ann_image(img_path: str, ann_path: str, ann_mtime: float, enhance: bool) -> bytes | None:
    """標注結果大圖，以 (img_path, ann_path, ann_mtime, enhance) 為 cache key。
    輸出限制在 1920×1440 JPEG，避免全解析度 PNG 造成大 WebSocket payload。
    """
    try:
        from PIL import Image
        label_data = json.loads(Path(ann_path).read_text(encoding="utf-8"))
        png_bytes = _draw_annotations(img_path, label_data, enhance=enhance)
        # 縮圖 + 轉 JPEG，大幅減少 WebSocket payload（PNG 全圖可達 5MB，JPEG 約 200-400KB）
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        img.thumbnail((1920, 1440), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()
    except Exception:
        return None


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
def _make_ann_thumb(file_path: str, ann_path: str, ann_mtime: float = 0.0) -> bytes | None:
    """標注結果縮圖（含框線），用於左欄列表。
    先縮圖到 120×90，再把座標等比縮小後畫框，避免對全解析度大圖做 PIL 操作。
    """
    try:
        from PIL import Image, ImageDraw, ImageOps
        label_data = json.loads(Path(ann_path).read_text(encoding="utf-8"))
        img = ImageOps.exif_transpose(Image.open(file_path)).convert("RGB")
        orig_w, orig_h = img.size
        img.thumbnail((120, 90), Image.LANCZOS)
        thumb_w, thumb_h = img.size
        sx = thumb_w / orig_w
        sy = thumb_h / orig_h

        draw = ImageDraw.Draw(img)
        colour_map: dict[str, tuple] = {}
        for shape in label_data.get("shapes", []):
            label      = shape.get("label", "?")
            shape_type = shape.get("shape_type", "")
            points     = shape.get("points", [])
            if label not in colour_map:
                colour_map[label] = _PALETTE[len(colour_map) % len(_PALETTE)]
            c = colour_map[label]
            if shape_type == "rectangle" and len(points) >= 2:
                xs = [p[0] * sx for p in points]
                ys = [p[1] * sy for p in points]
                draw.rectangle([min(xs), min(ys), max(xs), max(ys)], outline=c, width=1)
            elif shape_type == "polygon" and len(points) >= 3:
                flat = [(p[0] * sx, p[1] * sy) for p in points]
                draw.polygon(flat, outline=c)

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
        img.thumbnail((480, 360), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        return None


@st.cache_data(show_spinner=False, max_entries=500)
def _make_ann_preview(file_path: str, ann_path: str, ann_mtime: float = 0.0) -> bytes | None:
    """先縮圖到 480×360 再畫框，避免對全解析度大圖做 PIL 操作。"""
    try:
        from PIL import Image, ImageDraw, ImageOps
        label_data = json.loads(Path(ann_path).read_text(encoding="utf-8"))
        img = ImageOps.exif_transpose(Image.open(file_path)).convert("RGB")
        orig_w, orig_h = img.size
        img.thumbnail((480, 360), Image.LANCZOS)
        thumb_w, thumb_h = img.size
        sx = thumb_w / orig_w
        sy = thumb_h / orig_h

        draw = ImageDraw.Draw(img)
        colour_map: dict[str, tuple] = {}
        for shape in label_data.get("shapes", []):
            label      = shape.get("label", "?")
            shape_type = shape.get("shape_type", "")
            points     = shape.get("points", [])
            if label not in colour_map:
                colour_map[label] = _PALETTE[len(colour_map) % len(_PALETTE)]
            c = colour_map[label]
            if shape_type == "rectangle" and len(points) >= 2:
                xs = [p[0] * sx for p in points]
                ys = [p[1] * sy for p in points]
                draw.rectangle([min(xs), min(ys), max(xs), max(ys)], outline=c, width=2)
            elif shape_type == "polygon" and len(points) >= 3:
                flat = [(p[0] * sx, p[1] * sy) for p in points]
                draw.polygon(flat, outline=c)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        return None


@st.cache_data(show_spinner=False, max_entries=200)
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


def _inject_img_click_zoom() -> None:
    """在 Streamlit doc 注入 MutationObserver：直接對 img.m012-zoomable 掛 click handler。

    改用 MutationObserver + 直接 addEventListener 取代事件委派，
    確保每次 Streamlit rerun 後的新圖片都能點擊放大。
    """
    components.html("""
<script>
(function() {
    var d = window.parent.document;
    if (d.getElementById('m012-lb')) return;

    // ── lightbox DOM ──────────────────────────────────────────────────
    var sty = d.createElement('style');
    sty.id = 'm012-lb-sty';
    sty.textContent =
        '#m012-lb{display:none;position:fixed;inset:0;background:rgba(0,0,0,.9);' +
        'z-index:999999;cursor:zoom-out;align-items:center;justify-content:center;}' +
        '#m012-lb.on{display:flex;}' +
        '#m012-lb>img{max-width:95vw;max-height:95vh;object-fit:contain;border-radius:4px;}' +
        '#m012-lb-x{position:absolute;top:12px;right:20px;color:#fff;' +
        'font-size:32px;line-height:1;cursor:pointer;user-select:none;}';
    d.head.appendChild(sty);

    var lb = d.createElement('div'); lb.id = 'm012-lb';
    var lbX = d.createElement('span'); lbX.id = 'm012-lb-x'; lbX.textContent = '✕';
    var lbImg = d.createElement('img'); lbImg.id = 'm012-lb-img';
    lb.appendChild(lbX); lb.appendChild(lbImg);
    d.body.appendChild(lb);

    function open(src) { lbImg.src = src; lb.classList.add('on'); }
    function close()   { lb.classList.remove('on'); }

    lb.addEventListener('click', function(e) {
        if (e.target === lb || e.target === lbX) close();
    });
    d.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') close();
    });

    // ── 直接掛 handler 到每個 img.m012-zoomable（含 rerun 後新產生的）──
    function attach(img) {
        if (img.dataset.m012lb) return;
        img.dataset.m012lb = '1';
        img.style.cursor = 'zoom-in';
        img.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            open(img.src);
        });
    }
    function scan() {
        d.querySelectorAll('img.m012-zoomable').forEach(attach);
    }
    scan();
    new MutationObserver(scan).observe(d.body, {childList:true, subtree:true});
})();
</script>
""", height=0)


def _zoomable_img_html(img_bytes: bytes, mime: str = "jpeg") -> str:
    """回傳帶有 m012-zoomable class 的 <img>，點擊由 MutationObserver 附加的 handler 放大。"""
    b64 = base64.b64encode(img_bytes).decode()
    return (
        f'<img src="data:image/{mime};base64,{b64}"'
        f' class="m012-zoomable"'
        f' style="width:100%;max-height:52vh;object-fit:contain;border-radius:4px;display:block;"'
        f' title="點擊放大" />'
    )


def _thumb_html(thumb_bytes: bytes | None, img_path: str, tag: str,
                color: str, border: str, preview_bytes: bytes | None = None) -> str:
    if not thumb_bytes:
        return '<span style="color:#94a3b8;font-size:10px">—</span>'
    b64 = base64.b64encode(thumb_bytes).decode()
    img_tag = (
        f'<img src="data:image/jpeg;base64,{b64}"'
        f' style="max-height:80px;width:auto;border-radius:5px;'
        f'border:2px solid {border};display:block;cursor:zoom-in;" />'
    )
    if preview_bytes:
        p64 = base64.b64encode(preview_bytes).decode()
        hover = (
            f'<div class="m012-preview">'
            f'<img src="data:image/jpeg;base64,{p64}" />'
            f'<div style="margin-top:6px;font-size:12px;text-align:center;color:{color};'
            f'font-family:sans-serif;">{tag}</div>'
            f'</div>'
        )
    else:
        hover = ""
    return (
        f'<div class="m012-thumb" style="display:inline-block;text-align:center;position:relative;">'
        f'{img_tag}{hover}'
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

    // 將幽靈按鈕及其 wrapper 縮到 0 高度（height:0+overflow:hidden 才能消除 layout space）
    function hideGhosts() {
        d.querySelectorAll('button').forEach(function(b) {
            var txt = b.textContent.trim();
            if (txt === '← 上一張' || txt === '→ 下一張' ||
                /^[①②③④⑤⑥⑦⑧⑨]/.test(txt)) {
                b.style.cssText += ';opacity:0!important;pointer-events:none!important;' +
                    'position:absolute!important;left:-9999px!important;';
                var wrap = b.closest('[data-testid="stButton"]');
                if (wrap) wrap.style.cssText += ';height:0!important;min-height:0!important;' +
                    'overflow:hidden!important;margin:0!important;padding:0!important;' +
                    'border:0!important;line-height:0!important;';
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

def _check_pending_reload() -> bool:
    """若 module_019 已下載新資料集但 module_010 尚未重新載入，回傳 True。"""
    p = _cfg._CIM_LOG_DIR / "config" / "shared.json"
    if not p.exists():
        return False
    try:
        return bool(
            __import__("json").loads(p.read_text(encoding="utf-8")).get("pending_reload", False)
        )
    except Exception:
        return False


def render_output(result: dict) -> None:
    _help.render_help_button("module_012", "output", "🏷️ 標注進度")
    # 若 module_019 已下載新資料但 module_010 還沒重新載入，顯示警告並鎖定標注入口
    if _check_pending_reload():
        st.error(
            "⚠️ **資料集已更新**，請先前往 **Data Feeder**（第 2 個 Tab）"
            " 載入新資料後再繼續標注。",
        )
        st.stop()

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
    isat_exe               = result.get("isat_exe", "isat-sam")
    _log.info("[012] output render: annotation_tool=%s isat_exe=%s manifest=%s",
              annotation_tool, isat_exe, manifest_id)
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

    # 注入鍵盤快捷鍵 + 圖片點擊放大
    _keyboard_listener()
    _inject_img_click_zoom()

    # ── CSS ──────────────────────────────────────────────────────────────────
    st.markdown("""<style>
[data-testid='stImage'] img { max-height: 58vh; width: auto !important; object-fit: contain; }
.thumb-selected { border: 3px solid #1a73e8 !important; border-radius: 6px; padding: 2px; }
.m012-preview {
    display: none;
    position: fixed;
    left: min(46vw, 760px);
    top: 80px;
    z-index: 2147483000;
    max-width: min(50vw, 820px);
    background: #fff;
    border: 1.5px solid #94a3b8;
    border-radius: 8px;
    padding: 12px;
    box-shadow: 0 10px 36px rgba(15, 23, 42, .28);
    pointer-events: none;
}
.m012-preview img {
    display: block;
    max-width: min(48vw, 780px);
    max-height: 75vh;
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

    # 強化圖模式 sync：把 enhanced_dir 內的標注 JSON 回寫到原圖目錄
    # 條件：折疊區 toggle 啟用 OR 已有強化圖 JSON 存在（即使 toggle off 也清理一次）
    if manifest_id and annotation_tool == "x-anylabeling":
        _enh_dir_for_sync = _cfg.get_enhanced_dir(manifest_id)
        if _enh_dir_for_sync.exists() and any(_enh_dir_for_sync.glob("*.json")):
            _synced = _sync_enhanced_annotations(items, _enh_dir_for_sync)
            if _synced:
                _log.info("[012] enhanced→orig synced count=%d", _synced)
                # cache 失效讓下方 incremental refresh 重掃
                st.session_state.pop("m012_items", None)
                st.session_state.pop("m012_mtimes", None)
                items = _get_items(manifest_id, db_items)

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

    # 顯示上次操作留下的錯誤（st.rerun 前無法即時顯示，改用 session_state 跨 rerun）
    if _launch_ok := st.session_state.pop("m012_launch_ok", None):
        st.success(f"🖊 {_launch_ok}")
    if _launch_err := st.session_state.pop("m012_launch_error", None):
        st.error(f"啟動失敗：{_launch_err}")

    # pre-flight：ISAT 選為標注工具但 isat-sam 找不到時提早警告
    if annotation_tool == "isat" and not Path(isat_exe).exists() and not shutil.which(isat_exe):
        st.warning(
            f"⚠️ 找不到 ISAT 執行檔（`{isat_exe}`）。"
            " 請先安裝：`pip install isat-sam`，"
            "或在環境變數 `ISAT_EXE` 指定路徑後重新啟動 App。"
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
    # ── Progress + 操作按鈕同列 ─────────────────────────────────────────────
    _folder_proc = st.session_state.get("m012_folder_proc")
    _folder_active = _proc_alive(_folder_proc)
    # 清掉已結束的殘留引用；若 proc 是被外部關閉，通知使用者
    if not _folder_active and _folder_proc is not None:
        st.session_state["m012_folder_proc"] = None
        st.session_state.setdefault("m012_launch_ok", "資料夾標注已關閉（外部關閉 X-AnyLabeling）")
        _folder_proc = None

    _autorefresh_hint = f"自動掃描 {autorefresh_seconds}s" if autorefresh_enabled else "自動掃描：關閉"
    _prog_c, _btn_folder_c, _btn_update_c = st.columns([6, 2, 2], vertical_alignment="center")
    with _prog_c:
        st.progress(pct, text=f"已標注 {annotated} / {total} 張（{pct * 100:.1f}%）　·　{_autorefresh_hint}")
    with _btn_folder_c:
        if annotation_tool == "x-anylabeling":
            if _folder_active:
                if st.button("⏹ 關閉資料夾標注", key="m012_folder_close", use_container_width=True):
                    _folder_proc.terminate()
                    st.session_state["m012_folder_proc"] = None
                    st.session_state["m012_folder_enhanced_mode"] = False
                    st.session_state["m012_launch_ok"] = "資料夾標注已關閉"
                    st.rerun()
            else:
                # 是否使用強化圖模式：toggle on 且強化圖已產生完成才可進入
                _use_enh = bool(st.session_state.get("m012_use_enhanced", False))
                _enh_dir = _cfg.get_enhanced_dir(manifest_id) if manifest_id else None
                _enh_done, _enh_total = _enhanced_progress(items, _enh_dir) if _enh_dir else (0, len(items))
                _enh_ready = _use_enh and _enh_total > 0 and _enh_done == _enh_total
                _btn_label = "🗂️ 開啟資料夾標注（強化圖）" if _enh_ready else "🗂️ 開啟資料夾標注"
                _btn_disabled = _use_enh and not _enh_ready
                _btn_help = (
                    "請先在下方「強化圖批次標注」展開區產生完所有強化圖"
                    if _btn_disabled
                    else "以 X-AnyLabeling 開啟本 Manifest 的所有影像，標注後自動同步回 GUI"
                )
                if st.button(
                    _btn_label,
                    key="m012_folder_open",
                    use_container_width=True,
                    help=_btn_help,
                    disabled=_btn_disabled,
                ):
                    _folder_override = str(_enh_dir) if _enh_ready else None
                    with st.spinner("🚀 X-AnyLabeling 啟動中…首次約需 3-5 秒"):
                        _err, _proc = _launch_xany_folder(
                            items, labels, classes_path, xany_work_dir, xany_exe,
                            folder_override=_folder_override,
                        )
                    if _err:
                        st.session_state["m012_launch_error"] = _err
                    else:
                        st.session_state["m012_folder_proc"] = _proc
                        st.session_state["m012_folder_enhanced_mode"] = bool(_enh_ready)
                        st.session_state["m012_launch_ok"] = (
                            f"🚀 X-AnyLabeling 啟動中…（{len(items)} 張{'強化圖' if _enh_ready else '影像'}，視窗約 3-5 秒後出現）"
                        )
                    st.rerun()
        else:
            if st.button("重新掃描標注", key="m012_refresh_annotations", use_container_width=True):
                st.session_state.pop("m012_items", None)
                st.session_state.pop("m012_mtimes", None)
                st.session_state.pop("m012_cache_mid", None)
                st.rerun()
    with _btn_update_c:
        if st.button("➡️ 前往 Update", type="primary", key="m012_goto_update", use_container_width=True):
            _post_message("SWITCH_TAB", {"plugin_id": "module_013", "tab": "input"})

    if _folder_active:
        _enh_mode_active = bool(st.session_state.get("m012_folder_enhanced_mode", False))
        st.caption(
            f"🗂️ 資料夾標注模式執行中（{'強化圖' if _enh_mode_active else '原圖'}）— "
            "任何標注皆自動同步至 GUI"
            + ("，並回寫至原圖目錄" if _enh_mode_active else "")
        )
    elif annotation_tool != "x-anylabeling":
        st.caption("ℹ️ 目前標注工具不支援資料夾模式（僅 X-AnyLabeling 支援）")

    # ── 強化圖批次標注（可選）─────────────────────────────────────────────────
    if annotation_tool == "x-anylabeling" and manifest_id and not _folder_active:
        _enh_dir = _cfg.get_enhanced_dir(manifest_id)
        _enh_done, _enh_total = _enhanced_progress(items, _enh_dir)
        _expander_title = f"⚙️ 強化圖批次標注（可選）— 已產生 {_enh_done}/{_enh_total}"
        with st.expander(_expander_title, expanded=False):
            st.toggle(
                "啟用：用強化圖開啟資料夾標注",
                key="m012_use_enhanced",
                help="切換後上方按鈕會改用強化圖；標注完成的 JSON 會自動回寫到原圖目錄",
            )
            _gen_c1, _gen_c2 = st.columns([3, 5])
            with _gen_c1:
                _need_regen = _enh_done < _enh_total
                _gen_label = (
                    f"📸 產生強化圖（{_enh_total - _enh_done} 張待產生）"
                    if _need_regen else "📸 全部已產生（重新產生會覆蓋舊圖）"
                )
                if st.button(
                    _gen_label, key="m012_gen_enhanced",
                    use_container_width=True,
                    help=f"輸出至：{_enh_dir}",
                ):
                    _prog = st.progress(0.0, text="準備中…")
                    with st.spinner("📸 產生強化圖中…"):
                        _stats = _generate_enhanced_batch(items, _enh_dir, progress_placeholder=_prog)
                    _prog.empty()
                    st.session_state["m012_launch_ok"] = (
                        f"📸 強化圖完成：✅{_stats['ok']} ⏭️{_stats['skipped']} ❌{_stats['errors']}"
                    )
                    st.rerun()
            with _gen_c2:
                st.caption(
                    "💡 強化圖採用對比 ×2.2、飽和度 ×1.8（與 GUI 的「🔆 對比」一致）。"
                    "強化圖獨立存放於 cim_log，不會污染原圖目錄。"
                )

    # ── session_state：選取索引（m012_folder_proc 於上方 toolbar 區已初始化 via .get()）
    if "m012_selected_idx" not in st.session_state:
        st.session_state["m012_selected_idx"] = 0

    # ── 主體：左右欄 ─────────────────────────────────────────────────────────
    left_col, right_col = st.columns([1, 2], gap="medium")

    # ════════════════════════════════════════════════════════════════
    # 左欄：圖片列表
    # ════════════════════════════════════════════════════════════════
    with left_col:
        st.markdown("**圖片列表**")

        search_col, filter_col = st.columns([1, 1])
        with search_col:
            search_q = st.text_input(
                "搜尋檔名", value="", key="m012_search",
                placeholder="搜尋…", label_visibility="collapsed",
            ).strip().lower()
        with filter_col:
            filter_opt = st.selectbox(
                "狀態篩選",
                ["全部狀態", "⏳ 待標注", "✅ 已標注"],
                label_visibility="collapsed",
                key="m012_filter",
            )

        # 分類篩選 + AI 信心度篩選（同一行）— ratio 與上一列對齊
        clf_filter_options = ["全部分類", "（未分類）"] + (classification_labels or [])
        _clf_c, _ai_conf_c = st.columns([1, 1])
        with _clf_c:
            clf_filter = st.selectbox(
                "分類篩選",
                clf_filter_options,
                label_visibility="collapsed",
                key="m012_clf_filter",
            )
        with _ai_conf_c:
            ai_conf_filter = st.selectbox(
                "AI 信心度",
                ["全部 conf", "🤖 低 conf"],
                label_visibility="collapsed",
                key="m012_ai_conf_filter",
            )

        # 套用篩選
        visible = items
        if filter_opt == "⏳ 待標注":
            visible = [it for it in visible if not it["has_ann"]]
        elif filter_opt == "✅ 已標注":
            visible = [it for it in visible if it["has_ann"]]
        if clf_filter == "（未分類）":
            visible = [it for it in visible if not classifications.get(it.get("item_id", ""))]
        elif clf_filter != "全部分類":
            visible = [it for it in visible if classifications.get(it.get("item_id", "")) == clf_filter]
        if ai_conf_filter == "🤖 低 conf":
            def _low_conf(it: dict) -> bool:
                try:
                    meta = json.loads(it.get("metadata") or "{}")
                    mc = meta.get("max_conf", 0.0)
                    return 0 < mc < 0.5
                except Exception:
                    return False
            visible = [it for it in visible if _low_conf(it)]
        if search_q:
            visible = [it for it in visible if search_q in Path(it.get("file_path", "")).name.lower()]

        # 篩選切換時重設頁碼
        _filter_key = (filter_opt, clf_filter, search_q, ai_conf_filter)
        if st.session_state.get("m012_prev_filter") != _filter_key:
            st.session_state["m012_page"]        = 0
            st.session_state["m012_prev_filter"] = _filter_key

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
            # ─ 分頁控制列（上方）── 兼顯示總數 ─────────────────────
            if n_pages > 1:
                pg_prev, pg_info, pg_next = st.columns([1, 3, 1])
                with pg_prev:
                    if st.button("◀", key="m012_pg_prev_top", disabled=(page == 0),
                                 use_container_width=True):
                        st.session_state["m012_page"] = page - 1
                with pg_info:
                    st.caption(f"第 {page + 1}/{n_pages} 頁　共 {n_visible} 張")
                with pg_next:
                    if st.button("▶", key="m012_pg_next_top", disabled=(page == n_pages - 1),
                                 use_container_width=True):
                        st.session_state["m012_page"] = page + 1
            else:
                st.caption(f"共 {n_visible} 張")

            # ─ AI label 按鈕 + inline 模型資訊 ───────────────────────
            _ai_cfg_now = _ai_cfg.load_config()
            _ai_model = _ai_cfg_now.get("model_path", "")
            _conf_now  = float(_ai_cfg_now.get("conf_threshold", 0.25))
            _ai_model_name = Path(_ai_model).name if _ai_model else "未設定"
            if _ai_model and Path(_ai_model).exists():
                _ai_info_c, _ai_btn_c = st.columns([1, 1], vertical_alignment="center")
                _ai_info_c.caption(f"⚡ `{_ai_model_name}`　conf {_conf_now:.2f}")
                if _ai_btn_c.button(
                    f"⚡ AI label 本頁（{len(page_items)}）",
                    key="m012_ai_page", use_container_width=True,
                    help=f"對當頁 {len(page_items)} 張用模型 {_ai_model_name} 推論（conf {_conf_now:.2f}）",
                ):
                    _prog = st.progress(0.0, text="準備中…")
                    _stats = _run_ai_items(
                        list(page_items),
                        _ai_model,
                        _ai_cfg_now.get("model_type", "yolo"),
                        float(_ai_cfg_now.get("conf_threshold", 0.25)),
                        bool(_ai_cfg_now.get("overwrite_existing", False)),
                        progress_placeholder=_prog,
                    )
                    _prog.empty()
                    _det_b = _stats.get("detected", 0)
                    _cls_b = _stats.get("model_class_names", [])
                    if _det_b == 0 and _stats.get("ok", 0) > 0:
                        st.warning(
                            f"⚠️ 當頁 {_stats['ok']} 張圖均未偵測到任何物件。\n\n"
                            f"此模型可偵測的類別：`{'、'.join(_cls_b[:10])}{'…' if len(_cls_b) > 10 else ''}`\n\n"
                            "若您的圖片不屬於上述類別，請先手動標注再訓練專屬模型。"
                            if _cls_b else
                            f"⚠️ 當頁 {_stats['ok']} 張圖均未偵測到任何物件。"
                            "此模型可能尚未針對您的資料集訓練。"
                        )
                    else:
                        st.toast(
                            f"完成 — 偵測 {_det_b} 個物件　✅{_stats['ok']} ⏭️{_stats['skipped']} ❌{_stats['errors']}",
                            icon="⚡",
                        )
                    st.session_state.pop("m012_items", None)
                    st.session_state.pop("m012_mtimes", None)
                    st.rerun()
            else:
                st.caption("⚡ 請先在右欄 AI 設定選擇模型")

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
                    _make_ann_thumb(fp, item["ann_path"], item.get("ann_mtime", 0.0))
                    if has_ann and item["ann_path"] else None
                )
                ann_preview_bytes = (
                    _make_ann_preview(fp, item["ann_path"], item.get("ann_mtime", 0.0))
                    if has_ann and item["ann_path"] else None
                )

                # 縮圖（點 ▶ 選取）| 標注縮圖 | 檔名 + 狀態 + 操作按鈕
                thumb_c, ann_c, info_c = st.columns([1, 1, 3])
                with thumb_c:
                    if thumb_bytes:
                        st.image(thumb_bytes, width=120)
                    else:
                        st.caption("—")
                    # ▶ 選取按鈕放縮圖正下方
                    if st.button(
                        "▶ 選取" if not is_selected else "● 已選",
                        key=f"sel_{item['item_id']}",
                        type="primary" if is_selected else "secondary",
                        use_container_width=True,
                    ):
                        st.session_state["m012_selected_idx"] = global_idx
                        st.rerun()

                with ann_c:
                    if ann_thumb_bytes:
                        st.image(ann_thumb_bytes, width=120)
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

                    # 兩個操作按鈕：🖊 標注工具 | ⚡ AI 標注
                    _item_folder_active = _proc_alive(
                        st.session_state.get("m012_folder_proc")
                    ) and annotation_tool == "x-anylabeling"
                    _item_enh_mode = _item_folder_active and bool(
                        st.session_state.get("m012_folder_enhanced_mode", False)
                    )
                    btn_ann, btn_ai = st.columns(2)
                    with btn_ann:
                        if st.button(
                            "🖊 標注工具",
                            key=f"xany_{item['item_id']}",
                            use_container_width=True,
                        ):
                            st.session_state["m012_selected_idx"] = global_idx
                            if _item_folder_active:
                                _target_fp = fp
                                if _item_enh_mode and manifest_id:
                                    _enh_cand = _cfg.get_enhanced_dir(manifest_id) / Path(fp).name
                                    if _enh_cand.exists():
                                        _target_fp = str(_enh_cand)
                                _relaunch_xany_at(
                                    _target_fp, labels, classes_path, xany_work_dir, xany_exe,
                                )
                            else:
                                with st.spinner(f"🚀 啟動標注工具中…首次約需 3-5 秒"):
                                    tool_name, err = _launch_annotation_tool(
                                        annotation_tool, fp, labels, classes_path,
                                        xany_work_dir, xany_exe, labelme_exe,
                                        isat_exe=isat_exe,
                                        ann_path=item["ann_path"],
                                    )
                                if err:
                                    st.session_state["m012_launch_error"] = err
                                else:
                                    st.session_state["m012_launch_ok"] = (
                                        f"🚀 {tool_name} 啟動中…（{fname}，視窗約 3-5 秒後出現）"
                                    )
                            st.rerun()
                    with btn_ai:
                        if st.button(
                            "⚡ AI 標注",
                            key=f"ai_{item['item_id']}",
                            use_container_width=True,
                            disabled=not bool(_ai_model),
                            help="對此張執行 AI 預標注" if _ai_model else "請先在頂部設定 AI 模型",
                        ):
                            with st.spinner("AI 標注中…"):
                                _stats = _run_ai_items(
                                    [item], _ai_model,
                                    _ai_cfg_now.get("model_type", "yolo"),
                                    float(_ai_cfg_now.get("conf_threshold", 0.25)),
                                    bool(_ai_cfg_now.get("overwrite_existing", False)),
                                )
                            st.session_state.pop("m012_items", None)
                            st.session_state.pop("m012_mtimes", None)
                            det = _stats.get("detected", 0)
                            st.session_state["m012_launch_ok"] = f"AI 完成：偵測 {det} 個物件（{fname}）"
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

            # ── 單列 header：檔名 | 分類下拉 | 對比 toggle ──────────────────
            parts = Path(fp).parts if fp else ()
            short = str(Path(*parts[-3:])) if len(parts) >= 3 else fp
            item_id = item.get("item_id", "")
            n_items = len(items)

            if classification_labels:
                fname_c, clf_c, enhance_c = st.columns([3, 3, 1.5])
            else:
                fname_c, enhance_c = st.columns([5, 1.5])
                clf_c = None

            with fname_c:
                st.markdown(f"**{fname}**  \n`{short}`")

            with enhance_c:
                enhance = st.toggle(
                    "🔆 對比",
                    key=f"enhance_{item['item_id']}",
                    help="強化對比度與飽和度（僅影響標注結果顯示）",
                )

            if clf_c is not None:
                current_clf = classifications.get(item_id, "")

                def _display(i: int, lbl: str) -> str:
                    return f"[{i+1}] {lbl}" if i < 9 else lbl

                clf_display = ["請選擇分類"] + [
                    _display(i, lbl) for i, lbl in enumerate(classification_labels)
                ]
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
                    import re as _re
                    raw = _re.sub(r"^\[\d+\] ", "", chosen)
                    _save_clf(manifest_id, item_id, raw, classifications, file_path=fp)
                    st.session_state["m012_selected_idx"] = _next_unclassified(
                        items, sel_idx, classifications
                    )

                with clf_c:
                    clf_sel_c, clf_rst_c = st.columns([5, 1])
                    with clf_sel_c:
                        st.selectbox(
                            "分類", clf_display, index=clf_default,
                            key=f"clf_sel_{item_id}",
                            label_visibility="collapsed",
                            on_change=_on_clf_change,
                        )
                    with clf_rst_c:
                        if current_clf and st.button(
                            "✕", use_container_width=True,
                            key=f"clf_reset_{item_id}",
                            help="清除分類",
                        ):
                            _clear_clf(manifest_id, item_id, classifications, file_path=fp)
                            st.rerun()

            st.divider()

            # ── AI Pre-label 面板 ─────────────────────────────────────────
            _ai_c = _ai_cfg.load_config()
            _ai_type_key = _ai_c.get("model_type", "yolo")
            with st.expander(
                f"⚙️ AI 模型設定（{_ai_type_key.upper()}）", expanded=False,
            ):
                # 模型路徑
                if "_m012_ai_model_chosen" in st.session_state:
                    st.session_state["m012_ai_model_path"] = st.session_state.pop("_m012_ai_model_chosen")
                if "m012_ai_model_path" not in st.session_state:
                    st.session_state["m012_ai_model_path"] = _ai_c.get("model_path", "")

                # 第 1 列：模型路徑 + 📂
                _mp_col, _br_col = st.columns([7, 1])
                with _mp_col:
                    _ai_model_path = st.text_input(
                        "模型路徑（.pt）", key="m012_ai_model_path",
                        placeholder="C:/models/best.pt", label_visibility="collapsed",
                    )
                with _br_col:
                    if st.button("📂", key="m012_ai_browse",
                                 help="瀏覽 .pt 模型檔（YOLO / Classifier 可在 AI Pre-labeling 頁切換）"):
                        try:
                            _chosen = subprocess.run(
                                [sys.executable, "-c",
                                 "import tkinter as tk; from tkinter import filedialog; "
                                 "root=tk.Tk(); root.withdraw(); root.wm_attributes('-topmost',True); "
                                 "p=filedialog.askopenfilename(title='選擇模型',filetypes=[('PyTorch model','*.pt'),('All','*.*')]); "
                                 "root.destroy(); print(p or '',end='')"],
                                capture_output=True, text=True, timeout=60,
                            ).stdout.strip()
                            if _chosen:
                                st.session_state["_m012_ai_model_chosen"] = _chosen
                                st.rerun()
                        except Exception:
                            pass

                # 第 2 列：Confidence slider + 覆蓋已有標注 checkbox（同列）
                _conf_col, _ow_col = st.columns([3, 2], vertical_alignment="center")
                with _conf_col:
                    _ai_conf = st.slider(
                        "Confidence", 0.01, 1.0,
                        value=float(_ai_c.get("conf_threshold", 0.25)),
                        step=0.05, format="%.2f", key="m012_ai_conf",
                    )
                with _ow_col:
                    _ai_overwrite = st.checkbox(
                        "覆蓋已有標注", value=bool(_ai_c.get("overwrite_existing", False)),
                        key="m012_ai_overwrite",
                    )

                # 只有在值有變動時才寫檔
                _new_vals = {"model_path": _ai_model_path,
                             "conf_threshold": _ai_conf,
                             "overwrite_existing": _ai_overwrite}
                if any(_ai_c.get(k) != v for k, v in _new_vals.items()):
                    try:
                        _ai_c.update(_new_vals)
                        _ai_cfg.save_config(_ai_c)
                    except Exception:
                        pass

                # 單張 AI 按鈕
                if _ai_model_path and Path(_ai_model_path).exists() and fp and Path(fp).exists():
                    if st.button("⚡ 對此圖執行 AI Pre-label", key="m012_ai_single",
                                 use_container_width=True):
                        _prog_s = st.progress(0.0, text="載入模型中…")
                        _s = _run_ai_items(
                            [item], _ai_model_path, _ai_type_key,
                            _ai_conf, _ai_overwrite,
                            progress_placeholder=_prog_s,
                        )
                        _prog_s.empty()
                        if _s.get("error_detail"):
                            st.error(_s["error_detail"])
                        else:
                            _det = _s.get("detected", 0)
                            _cls = _s.get("model_class_names", [])
                            if _det == 0 and _s.get("ok", 0) > 0:
                                st.warning(
                                    f"⚠️ 此圖未偵測到任何物件（confidence ≥ {_ai_conf:.2f}）。\n\n"
                                    f"**可能原因：**\n"
                                    f"- 此模型（`{Path(_ai_model_path).name}`）尚未針對您的資料集訓練，"
                                    f"只能偵測它原本學過的類別。\n"
                                    + (f"- 此模型可偵測的類別：`{'、'.join(_cls[:10])}{'…' if len(_cls) > 10 else ''}`\n" if _cls else "")
                                    + f"- 若您的圖片內容不屬於上述類別，模型不會有輸出。\n\n"
                                    f"**建議：** 使用「🖊 標注工具」手動標注幾張後，再透過 Training 頁訓練專屬模型。"
                                )
                            else:
                                st.toast(
                                    f"偵測到 {_det} 個物件　✅{_s.get('ok',0)} ⏭️{_s.get('skipped',0)} ❌{_s.get('errors',0)}",
                                    icon="⚡",
                                )
                        st.session_state.pop("m012_items", None)
                        st.session_state.pop("m012_mtimes", None)
                        st.rerun()
                else:
                    st.caption("請選擇模型檔案後才能推論")

            st.divider()

            # ── 資料夾模式：切換到此圖按鈕（緊貼圖片上方，凸顯層次感）─────────
            if _proc_alive(st.session_state.get("m012_folder_proc")) and fp and Path(fp).exists():
                _nav_c1, _nav_c2 = st.columns([3, 5])
                _nav_enh_mode = bool(st.session_state.get("m012_folder_enhanced_mode", False))
                with _nav_c1:
                    if st.button(
                        "🎯 切換到此圖",
                        key=f"m012_nav_{item_id}",
                        use_container_width=True,
                        help="重啟 X-AnyLabeling 並開啟此圖（約需 3-5 秒）",
                    ):
                        _nav_target_fp = fp
                        if _nav_enh_mode and manifest_id:
                            _nav_enh_cand = _cfg.get_enhanced_dir(manifest_id) / Path(fp).name
                            if _nav_enh_cand.exists():
                                _nav_target_fp = str(_nav_enh_cand)
                        _relaunch_xany_at(_nav_target_fp, labels, classes_path, xany_work_dir, xany_exe)
                        st.rerun()
                with _nav_c2:
                    st.caption(
                        "💡 較快的方法：直接在 X-AnyLabeling 視窗內用左側列表切換影像"
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
                        st.caption("**原圖**（點擊放大）")
                        orig_full = _make_full_jpeg(fp)
                        if orig_full:
                            st.markdown(_zoomable_img_html(orig_full, "jpeg"), unsafe_allow_html=True)
                        else:
                            st.image(fp, use_container_width=True)
                    with ann_c:
                        st.caption("**標注結果**（點擊放大）")
                        try:
                            _ann_mtime = Path(ann_path).stat().st_mtime if ann_path else 0.0
                            ann_bytes = _cached_ann_image(fp, ann_path, _ann_mtime, enhance)
                            if ann_bytes:
                                st.markdown(_zoomable_img_html(ann_bytes, "jpeg"), unsafe_allow_html=True)
                            else:
                                st.image(fp, use_container_width=True)
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
                    # ann_path 存在但 shapes 為空（可能是 AI 推論後未偵測到物件）
                    _right_panel_img(fp, enhance, item_id=item_id)
                    st.info("此圖尚無標注框。若剛執行過 AI Pre-label，表示模型在此圖未偵測到物件（可嘗試降低 Confidence 門檻）。如需手動標注，請使用「🖊 標注工具」。")
            else:
                # 無標注
                _right_panel_img(fp, enhance, item_id=item_id)
                st.info("此圖尚無標注，點擊左側「🖊 標注工具」開始標注。")

            # ── 幽靈按鈕（最底部，JS 隱藏，鍵盤快捷鍵用） ───────────────────
            if st.button("← 上一張", key="m012_prev_btn"):
                st.session_state["m012_selected_idx"] = (sel_idx - 1) % n_items
                st.session_state["m012_kbd_nav"] = True
            if st.button("→ 下一張", key="m012_next_btn"):
                st.session_state["m012_selected_idx"] = (sel_idx + 1) % n_items
                st.session_state["m012_kbd_nav"] = True
            if classification_labels:
                _syms = ["①","②","③","④","⑤","⑥","⑦","⑧","⑨"]
                for _qi, _lbl in enumerate(classification_labels[:9]):
                    if st.button(f"{_syms[_qi]} {_lbl}", key=f"qc_{item_id}_{_qi}"):
                        _save_clf(manifest_id, item_id, _lbl, classifications, file_path=fp)
                        st.session_state["m012_selected_idx"] = _next_unclassified(
                            items, sel_idx, classifications
                        )
                        st.rerun()
