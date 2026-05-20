from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path


_HERE = Path(__file__).resolve().parent


def _load_output_module():
    spec = importlib.util.spec_from_file_location(
        "_012_output_for_test", _HERE / "012_output.py"
    )
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

    err = mod._launch_xany(
        str(img),
        ["defect"],
        str(classes),
        str(tmp_path / "xany-state"),
        str(xany_exe),
    )

    assert err is None
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
