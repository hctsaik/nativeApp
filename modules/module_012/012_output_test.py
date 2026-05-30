from __future__ import annotations

import importlib.util
import json
import os
import shutil
from pathlib import Path


_HERE = Path(__file__).resolve().parent
_CFG_PATH = _HERE / "_config.py"


def _load_output_module():
    spec = importlib.util.spec_from_file_location(
        "_012_output_for_test", _HERE / "012_output.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_output_module_with_cim_log(cim_log: Path, suffix: str = ""):
    """Load 012_output.py with CIM_LOG_DIR pointing to cim_log (set before exec)."""
    spec = importlib.util.spec_from_file_location(
        f"_012_output_clf_test{suffix}", _HERE / "012_output.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_cfg_module(cim_log: Path, suffix: str = ""):
    spec = importlib.util.spec_from_file_location(f"_012_cfg_test{suffix}", _CFG_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_output_detects_same_directory_xanylabeling_json(tmp_path):
    mod = _load_output_module()
    img = tmp_path / "frame_000001.jpg"
    img.write_bytes(b"fake image bytes")
    ann = img.with_suffix(".json")
    ann.write_text(
        json.dumps(
            {
                "imagePath": img.name,
                "shapes": [{"label": "defect", "points": [[1, 2], [3, 4]]}],
            }
        ),
        encoding="utf-8",
    )

    has_ann, ann_path, shape_count = mod._find_annotation(str(img))

    assert has_ann is True
    assert ann_path == str(ann)
    assert shape_count == 1


def test_output_ignores_non_same_directory_annotations(tmp_path):
    mod = _load_output_module()
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    external_dir = tmp_path / "external"
    ann_dir = external_dir / "annotations"
    ann_dir.mkdir(parents=True)

    img = source_dir / "frame_000001.jpg"
    img.write_bytes(b"fake image bytes")
    ann = ann_dir / "frame_000001.json"
    ann.write_text(
        json.dumps(
            {
                "imagePath": str(img),
                "shapes": [{"label": "defect", "points": [[1, 2], [3, 4]]}],
            }
        ),
        encoding="utf-8",
    )

    has_ann, ann_path, shape_count = mod._find_annotation(str(img))

    assert has_ann is False
    assert ann_path == ""
    assert shape_count == 0


def test_thumb_html_contains_css_hover_preview():
    mod = _load_output_module()

    html = mod._thumb_html(
        b"thumb",
        img_path="image.jpg",
        tag="image.jpg",
        color="#1a73e8",
        border="#cbd5e1",
        preview_bytes=b"preview",
    )

    assert "m012-thumb" in html
    assert "m012-preview" in html
    assert "cursor:zoom-in" in html
    assert "image.jpg" in html


def test_launch_annotation_tool_dispatches_to_labelme(tmp_path, monkeypatch):
    mod = _load_output_module()
    img = tmp_path / "frame_000001.jpg"
    img.write_bytes(b"fake image bytes")
    classes = tmp_path / "classes.txt"
    classes.write_text("defect", encoding="utf-8")
    exe = tmp_path / "labelme.exe"
    exe.write_bytes(b"fake exe")

    launched = []

    class _FakeProc:
        pass

    def _fake_popen(cmd):
        launched.append(cmd)
        return _FakeProc()

    monkeypatch.setattr(mod.subprocess, "Popen", _fake_popen)

    tool_name, err = mod._launch_annotation_tool(
        "labelme",
        str(img),
        ["defect"],
        str(classes),
        str(tmp_path / "xany-state"),
        "xanylabeling",
        str(exe),
    )

    assert err is None
    assert tool_name == "LabelMe"
    assert launched
    assert str(exe) == launched[0][0]
    assert "--output" in launched[0]
    assert str(img.with_suffix(".json")) in launched[0]


def test_launch_annotation_tool_defaults_to_xanylabeling(tmp_path, monkeypatch):
    mod = _load_output_module()
    img = tmp_path / "frame_000001.jpg"
    img.write_bytes(b"fake image bytes")
    xany_exe = tmp_path / ".venv-xanylabeling" / "Scripts" / "xanylabeling.exe"
    xany_exe.parent.mkdir(parents=True)
    xany_exe.write_bytes(b"fake exe")
    (xany_exe.parents[1] / "pyvenv.cfg").write_text("version_info = 3.11.9", encoding="utf-8")

    launched = []

    class _FakeProc:
        pass

    monkeypatch.setattr(mod, "_find_venv_python_cmd", lambda _exe: ["py", "-3.11"])
    monkeypatch.setattr(mod.subprocess, "Popen", lambda cmd: launched.append(cmd) or _FakeProc())

    tool_name, err = mod._launch_annotation_tool(
        "x-anylabeling",
        str(img),
        ["defect"],
        "",
        str(tmp_path / "xany-state"),
        str(xany_exe),
        "labelme",
    )

    assert err is None
    assert tool_name == "X-AnyLabeling"
    assert launched
    assert launched[0][:3] == ["py", "-3.11", "-c"]


def test_find_venv_python_cmd_prefers_wdac_trusted_py_launcher(tmp_path, monkeypatch):
    mod = _load_output_module()
    xany_exe = tmp_path / ".venv-xanylabeling" / "Scripts" / "xanylabeling.exe"
    xany_exe.parent.mkdir(parents=True)
    xany_exe.write_bytes(b"fake exe")
    (xany_exe.parents[1] / "pyvenv.cfg").write_text(
        "version_info = 3.11.9\nhome = C:\\uv\\python\n",
        encoding="utf-8",
    )

    calls = []

    class _Result:
        returncode = 0

    monkeypatch.setattr(shutil, "which", lambda name: "C:\\Windows\\py.exe" if name == "py" else None)
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda cmd, capture_output=True, timeout=5: calls.append(cmd) or _Result(),
    )

    cmd = mod._find_venv_python_cmd(str(xany_exe))

    assert cmd == ["C:\\Windows\\py.exe", "-3.11"]
    assert calls == [["C:\\Windows\\py.exe", "-3.11", "--version"]]


def test_launch_xany_uses_security_flags_and_never_runs_trampoline_directly(tmp_path, monkeypatch):
    mod = _load_output_module()
    img = tmp_path / "images" / "frame_000001.jpg"
    img.parent.mkdir()
    img.write_bytes(b"fake image bytes")
    classes = tmp_path / "config" / "classes.txt"
    classes.parent.mkdir()
    classes.write_text("defect", encoding="utf-8")
    xany_exe = tmp_path / ".venv-xanylabeling" / "Scripts" / "xanylabeling.exe"
    xany_exe.parent.mkdir(parents=True)
    xany_exe.write_bytes(b"fake exe")
    (xany_exe.parents[1] / "pyvenv.cfg").write_text("version_info = 3.11.9", encoding="utf-8")

    launched = []

    class _FakeProc:
        pass

    monkeypatch.setattr(mod, "_find_venv_python_cmd", lambda _exe: ["py", "-3.11"])
    monkeypatch.setattr(mod.subprocess, "Popen", lambda cmd: launched.append(cmd) or _FakeProc())

    err, proc = mod._launch_xany(
        str(img),
        ["defect"],
        str(classes),
        str(tmp_path / "xany-state"),
        str(xany_exe),
    )

    assert err is None
    assert proc is not None
    cmd = launched[0]
    assert cmd[:3] == ["py", "-3.11", "-c"]
    assert str(xany_exe) not in cmd
    assert "from anylabeling.app import main; main()" in cmd[3]
    assert str(xany_exe.parents[1] / "Lib" / "site-packages") in cmd[3]
    assert "--filename" in cmd
    assert str(img) in cmd
    assert "--output" in cmd
    assert str(img.parent) in cmd
    assert "--work-dir" in cmd
    assert "--nodata" in cmd
    assert "--autosave" in cmd
    assert "--no-auto-update-check" in cmd
    assert "--labels" in cmd
    assert str(classes) in cmd
    assert "--validatelabel" in cmd
    assert "exact" in cmd


# ─── file_path-based 分類持久化測試 ──────────────────────────────────────────


def test_save_clf_writes_to_filepath_store_when_file_path_given(tmp_path, monkeypatch):
    """_save_clf with file_path also persists to module_012_classifications_by_path.json."""
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mod = _load_output_module_with_cim_log(cim_log, "_save_fp")

    img = tmp_path / "frame_00001.jpg"
    cache: dict = {}
    mod._save_clf("manifest_aaa", "item_001", "A", cache, file_path=str(img))

    # per-manifest store
    assert cache["item_001"] == "A"
    # file_path-based store
    by_path_file = cim_log / "config" / "module_012_classifications_by_path.json"
    assert by_path_file.exists(), "by_path store should be created"
    data = json.loads(by_path_file.read_text(encoding="utf-8"))
    assert data[str(img)] == "A"


def test_save_clf_skips_filepath_store_when_no_file_path_given(tmp_path, monkeypatch):
    """_save_clf without file_path must NOT create the by-path store (backward compat)."""
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mod = _load_output_module_with_cim_log(cim_log, "_save_no_fp")

    cache: dict = {}
    mod._save_clf("manifest_bbb", "item_001", "B", cache)  # no file_path

    assert cache["item_001"] == "B"
    by_path_file = cim_log / "config" / "module_012_classifications_by_path.json"
    assert not by_path_file.exists(), "by_path store should NOT be created when file_path is omitted"


def test_clear_clf_removes_from_filepath_store(tmp_path, monkeypatch):
    """_clear_clf with file_path removes the entry from the by-path store."""
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mod = _load_output_module_with_cim_log(cim_log, "_clear_fp")

    img = tmp_path / "frame_00001.jpg"
    cache: dict = {"item_001": "A"}

    # 先寫入 by_path store
    by_path_file = cim_log / "config" / "module_012_classifications_by_path.json"
    by_path_file.parent.mkdir(parents=True, exist_ok=True)
    by_path_file.write_text(json.dumps({str(img): "A"}), encoding="utf-8")

    mod._clear_clf("manifest_ccc", "item_001", cache, file_path=str(img))

    assert "item_001" not in cache
    data = json.loads(by_path_file.read_text(encoding="utf-8"))
    assert str(img) not in data, "cleared entry should be removed from by_path store"


def test_classification_survives_manifest_change_via_filepath_store(tmp_path, monkeypatch):
    """
    Core scenario: user classifies in manifest A, Data Feeder creates manifest B
    (same images, new item_ids). Classifications must still appear in manifest B
    via the file_path-based fallback merge.
    """
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mod = _load_output_module_with_cim_log(cim_log, "_survive_manifest")
    cfg = _load_cfg_module(cim_log, "_survive_cfg")

    img1 = tmp_path / "frame_00001.jpg"
    img2 = tmp_path / "frame_00002.jpg"

    # 在 manifest A 做分類
    cache_a: dict = {}
    mod._save_clf("manifest_A", "item_A1", "A", cache_a, file_path=str(img1))
    mod._save_clf("manifest_A", "item_A2", "B", cache_a, file_path=str(img2))

    # manifest B 有同樣的圖片，但 item_id 不同（Data Feeder 重新跑產生新 UUID）
    manifest_b_items = [
        {"item_id": "item_B1", "file_path": str(img1)},
        {"item_id": "item_B2", "file_path": str(img2)},
    ]
    classifications_b: dict = {}  # manifest B 本身沒有分類記錄

    # 模擬 render_output 的 file_path merge 邏輯
    fp_clf = cfg.load_classifications_by_path()
    for it in manifest_b_items:
        iid = it.get("item_id", "")
        if iid and iid not in classifications_b:
            fp = it.get("file_path", "")
            if fp and fp in fp_clf:
                classifications_b[iid] = fp_clf[fp]

    assert classifications_b["item_B1"] == "A", "frame_00001 should still be classified A in new manifest"
    assert classifications_b["item_B2"] == "B", "frame_00002 should still be classified B in new manifest"


# ─── 強化圖批次標注：產生 → 標注 → sync 回原圖 round-trip 測試 ──────────────────


def _make_real_image(path: Path, color=(40, 60, 80)) -> None:
    """寫一張真實可解碼的影像（供 PIL 強化用）。"""
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 24), color=color).save(path)


def _make_items(orig_dir: Path, n: int) -> list[dict]:
    items = []
    for i in range(n):
        fp = orig_dir / f"frame_{i:05d}.jpg"
        _make_real_image(fp, color=(20 + i * 10, 40, 60))
        items.append({"item_id": f"item_{i:05d}", "file_path": str(fp)})
    return items


def test_generate_enhanced_batch_creates_files_and_reports_counts(tmp_path):
    mod = _load_output_module()
    orig_dir = tmp_path / "orig"
    enhanced_dir = tmp_path / "enhanced"
    items = _make_items(orig_dir, 3)

    stats = mod._generate_enhanced_batch(items, enhanced_dir)

    assert stats == {"ok": 3, "skipped": 0, "errors": 0}
    for it in items:
        dst = enhanced_dir / Path(it["file_path"]).name
        assert dst.exists(), f"強化圖應產生：{dst}"
        # 強化後的位元組應與原圖不同（套用了對比/飽和度）
        assert dst.read_bytes() != Path(it["file_path"]).read_bytes()


def test_generate_enhanced_batch_skips_up_to_date_and_counts_missing_as_error(tmp_path):
    mod = _load_output_module()
    orig_dir = tmp_path / "orig"
    enhanced_dir = tmp_path / "enhanced"
    items = _make_items(orig_dir, 2)
    # 加一筆檔案不存在的 item，應計為 error
    items.append({"item_id": "ghost", "file_path": str(orig_dir / "missing.jpg")})

    first = mod._generate_enhanced_batch(items, enhanced_dir)
    assert first == {"ok": 2, "skipped": 0, "errors": 1}

    # 第二次跑：原圖未變動 → 既有強化圖較新 → 應跳過，不重做
    second = mod._generate_enhanced_batch(items, enhanced_dir)
    assert second == {"ok": 0, "skipped": 2, "errors": 1}


def test_enhanced_progress_counts_generated(tmp_path):
    mod = _load_output_module()
    orig_dir = tmp_path / "orig"
    enhanced_dir = tmp_path / "enhanced"
    items = _make_items(orig_dir, 4)

    assert mod._enhanced_progress(items, enhanced_dir) == (0, 4)
    mod._generate_enhanced_batch(items[:2], enhanced_dir)
    assert mod._enhanced_progress(items, enhanced_dir) == (2, 4)


def test_sync_enhanced_annotations_writes_back_to_original_dir(tmp_path):
    """完整 round-trip：強化圖目錄被標注後，JSON 同步回原圖目錄並改寫 imagePath。"""
    mod = _load_output_module()
    orig_dir = tmp_path / "orig"
    enhanced_dir = tmp_path / "enhanced"
    items = _make_items(orig_dir, 3)
    mod._generate_enhanced_batch(items, enhanced_dir)

    # 模擬使用者在 X-AnyLabeling 對「強化圖」標注：JSON 落在 enhanced_dir，
    # imagePath 指向強化圖檔名（X-AnyLabeling 行為）
    target = items[0]
    enh_stem = Path(target["file_path"]).stem
    enh_json = enhanced_dir / f"{enh_stem}.json"
    enh_json.write_text(
        json.dumps({
            "imagePath": f"{enh_stem}.jpg",
            "shapes": [{"label": "car", "shape_type": "rectangle",
                        "points": [[1, 2], [10, 12]]}],
        }),
        encoding="utf-8",
    )

    synced = mod._sync_enhanced_annotations(items, enhanced_dir)
    assert synced == 1

    orig_json = Path(target["file_path"]).with_suffix(".json")
    assert orig_json.exists(), "標注應同步回原圖目錄"
    data = json.loads(orig_json.read_text(encoding="utf-8"))
    # imagePath 必須改寫成原圖檔名（而非強化圖檔名）
    assert data["imagePath"] == Path(target["file_path"]).name
    assert data["shapes"][0]["label"] == "car"
    # 其餘未標注的原圖不應產生 JSON
    assert not Path(items[1]["file_path"]).with_suffix(".json").exists()


def test_sync_enhanced_annotations_is_idempotent(tmp_path):
    """第二次 sync 不應重複回寫（orig mtime >= enh mtime 時跳過）。"""
    mod = _load_output_module()
    orig_dir = tmp_path / "orig"
    enhanced_dir = tmp_path / "enhanced"
    items = _make_items(orig_dir, 1)
    mod._generate_enhanced_batch(items, enhanced_dir)

    enh_stem = Path(items[0]["file_path"]).stem
    enh_json = enhanced_dir / f"{enh_stem}.json"
    enh_json.write_text(
        json.dumps({"imagePath": f"{enh_stem}.jpg", "shapes": []}),
        encoding="utf-8",
    )

    assert mod._sync_enhanced_annotations(items, enhanced_dir) == 1
    # 沒有新標注 → 第二次應為 0
    assert mod._sync_enhanced_annotations(items, enhanced_dir) == 0

    # 強化圖標注又更新（mtime 變新）→ 再次 sync 應回寫
    orig_json = Path(items[0]["file_path"]).with_suffix(".json")
    new_mtime = orig_json.stat().st_mtime + 100
    os.utime(enh_json, (new_mtime, new_mtime))
    assert mod._sync_enhanced_annotations(items, enhanced_dir) == 1


def test_enhanced_to_original_map_maps_json_to_original(tmp_path):
    mod = _load_output_module()
    orig_dir = tmp_path / "orig"
    enhanced_dir = tmp_path / "enhanced"
    items = _make_items(orig_dir, 2)

    mapping = mod._enhanced_to_original_map(items, enhanced_dir)

    for it in items:
        enh_json = enhanced_dir / (Path(it["file_path"]).stem + ".json")
        assert mapping[str(enh_json)] == it["file_path"]
