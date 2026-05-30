"""Tests for core.external_gui — the reusable external-GUI launcher.

These pin the Round-1 fix that turns the Label tool's hand-written
external-program launch logic into a reusable, declarative capability
(docs/platform/selfbuild-tool-shipping-evaluation.md, gap #3 / scenario S3).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core import external_gui as eg


# ── normalize_spec ────────────────────────────────────────────────────────────


def test_normalize_spec_fills_defaults():
    s = eg.normalize_spec({"exe_fallback": "mytool", "args": ["--x", "{v}"]})
    assert s["clean_python_env"] is True
    assert s["single_instance"] is True
    assert s["args"] == ["--x", "{v}"]
    assert s["button_label"].startswith("▶")


@pytest.mark.parametrize("bad,msg", [
    ("notadict", "dict"),
    ({}, "exe"),
    ({"exe_fallback": "x", "args": "nope"}, "args"),
    ({"exe_fallback": "x", "collect": {"glob": "*"}}, "collect"),
])
def test_normalize_spec_rejects_bad(bad, msg):
    with pytest.raises(eg.ExternalGuiSpecError) as exc:
        eg.normalize_spec(bad)
    assert msg in str(exc.value)


# ── resolve_exe ───────────────────────────────────────────────────────────────


def test_resolve_exe_env_var_wins(tmp_path, monkeypatch):
    real = tmp_path / "real.exe"
    real.write_text("x")
    monkeypatch.setenv("MY_EXE", str(real))
    assert eg.resolve_exe("MY_EXE", ["nope"], "fallback") == str(real)


def test_resolve_exe_candidate_when_exists(tmp_path):
    cand = tmp_path / "tool.exe"
    cand.write_text("x")
    assert eg.resolve_exe(None, [str(cand)], "fallback") == str(cand)


def test_resolve_exe_falls_back_to_bare_name():
    assert eg.resolve_exe("UNSET_VAR", ["/nonexistent/x"], "mytool") == "mytool"


# ── command_prefix (WDAC-safe) ────────────────────────────────────────────────


def test_command_prefix_uses_sibling_python_when_module_given(tmp_path):
    exe = tmp_path / "xanylabeling.exe"
    exe.write_text("x")
    py_name = "python.exe" if os.name == "nt" else "python"
    (tmp_path / py_name).write_text("x")
    prefix = eg.command_prefix(str(exe), python_module="anylabeling.app")
    assert prefix[-2:] == ["-m", "anylabeling.app"]
    assert prefix[0].endswith(py_name)


def test_command_prefix_plain_exe_without_module(tmp_path):
    exe = tmp_path / "tool.exe"
    exe.write_text("x")
    assert eg.command_prefix(str(exe)) == [str(exe)]


# ── interpolate_args ──────────────────────────────────────────────────────────


def test_interpolate_args_fills_params():
    out = eg.interpolate_args(["--in", "{input_dir}", "--n", 3], {"input_dir": "C:/d"})
    assert out == ["--in", "C:/d", "--n", "3"]


def test_interpolate_args_unknown_key_raises():
    with pytest.raises(eg.ExternalGuiSpecError):
        eg.interpolate_args(["{missing}"], {"present": 1})


# ── plan_env ──────────────────────────────────────────────────────────────────


def test_plan_env_sanitizes_python_vars():
    base = {"PYTHONPATH": "/poison", "PYTHONHOME": "/h", "PATH": "/bin"}
    env = eg.plan_env("mytool", clean_python_env=True, prepend_exe_dir=False, base_env=base)
    assert "PYTHONPATH" not in env and "PYTHONHOME" not in env
    assert env["PYTHONNOUSERSITE"] == "1"


def test_plan_env_prepends_exe_dir(tmp_path):
    exe = tmp_path / "bin" / "tool.exe"
    exe.parent.mkdir()
    exe.write_text("x")
    env = eg.plan_env(str(exe), prepend_exe_dir=True, base_env={"PATH": "/old"})
    assert env["PATH"].startswith(str(exe.parent.resolve()))


# ── build_launch (end-to-end pure) ────────────────────────────────────────────


def test_build_launch_combines_everything(tmp_path):
    exe = tmp_path / "tool.exe"
    exe.write_text("x")
    spec = {"exe_candidates": [str(exe)], "args": ["--out", "{out}"]}
    plan = eg.build_launch(spec, {"out": "D:/results"})
    assert plan["exe"] == str(exe)
    assert plan["cmd"] == [str(exe), "--out", "D:/results"]
    assert plan["env"]["PYTHONNOUSERSITE"] == "1"


def test_build_launch_no_exe_raises():
    with pytest.raises(eg.ExternalGuiSpecError):
        eg.build_launch({"exe_fallback": ""}, {})


# ── collect_outputs ───────────────────────────────────────────────────────────


def test_collect_outputs_parses_and_skips_failures(tmp_path):
    (tmp_path / "a.json").write_text('{"n": 1}')
    (tmp_path / "b.json").write_text("not json")
    import json
    out = eg.collect_outputs(tmp_path, "*.json", parser=lambda f: json.loads(f.read_text()))
    assert out == [{"n": 1}]  # b.json skipped, not fatal


def test_collect_outputs_missing_dir_returns_empty():
    assert eg.collect_outputs("/no/such/dir") == []


# ── render_launcher (Streamlit adapter) ───────────────────────────────────────


class _FakeExpander:
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


class _FakeSt:
    def __init__(self, click=False):
        self._click = click
        self.errors: list[str] = []
        self.successes: list[str] = []
        self.warnings: list[str] = []

    def button(self, *a, **k):
        return self._click

    def expander(self, *a, **k):
        return _FakeExpander()

    def write(self, *a, **k):
        pass

    def code(self, *a, **k):
        pass

    def error(self, msg):
        self.errors.append(msg)

    def success(self, msg):
        self.successes.append(msg)

    def warning(self, msg):
        self.warnings.append(msg)


def test_render_launcher_no_click_is_noop(tmp_path):
    exe = tmp_path / "t.exe"; exe.write_text("x")
    st = _FakeSt(click=False)
    res = eg.render_launcher({"exe_candidates": [str(exe)]}, {}, st)
    assert res["ok"] is None and not st.errors


def test_render_launcher_click_launches(tmp_path, monkeypatch):
    exe = tmp_path / "t.exe"; exe.write_text("x")
    captured = {}

    def fake_launch(cmd, env=None, key=None, single_instance=False, **kw):
        captured["cmd"] = cmd
        return {"ok": True, "pid": 4321, "error": None}

    monkeypatch.setattr(eg, "launch", fake_launch)
    st = _FakeSt(click=True)
    res = eg.render_launcher({"exe_candidates": [str(exe)], "args": ["--go"]}, {}, st)
    assert res["ok"] is True and res["pid"] == 4321
    assert captured["cmd"][-1] == "--go"
    assert st.successes


def test_render_launcher_collects_outputs_on_close(tmp_path, monkeypatch):
    """The no-code path must recover output files when the program closes
    (the full launch→work→close→recover loop, not just launch)."""
    exe = tmp_path / "t.exe"; exe.write_text("x")
    out_dir = tmp_path / "out"; out_dir.mkdir()
    (out_dir / "r1.json").write_text("{}")
    (out_dir / "r2.json").write_text("{}")

    monkeypatch.setattr(eg, "launch",
                        lambda *a, **k: {"ok": True, "pid": 99, "error": None})
    # watch_pid fires the close callback immediately (simulates program exit)
    monkeypatch.setattr(eg, "watch_pid", lambda pid, on_close, **k: on_close(pid))

    collected = {}
    spec = {"exe_candidates": [str(exe)],
            "collect": {"dir": str(out_dir), "glob": "*.json"}}
    eg.render_launcher(spec, {}, _FakeSt(click=True),
                       on_result=lambda files: collected.update(n=len(files)))
    assert collected.get("n") == 2, "collect_outputs must run on close and feed on_result"


def test_resolve_collect_dir_interpolates():
    norm = eg.normalize_spec({"exe_fallback": "x", "collect": {"dir": "{out}/sub"}})
    assert eg.resolve_collect_dir(norm, {"out": "D:/data"}) == "D:/data/sub"


# ── declarative collect parser ────────────────────────────────────────────────


def test_normalize_spec_rejects_unknown_parse():
    with pytest.raises(eg.ExternalGuiSpecError) as exc:
        eg.normalize_spec({"exe_fallback": "x", "collect": {"dir": "d", "parse": "xml"}})
    assert "parse" in str(exc.value)


def test_make_parser_json_and_none():
    assert eg.make_parser(None) is None
    assert callable(eg.make_parser("json"))


def test_collect_outputs_with_declared_json_parser(tmp_path):
    (tmp_path / "a.json").write_text('{"k": 1}')
    (tmp_path / "b.json").write_text('{"k": 2}')
    out = eg.collect_outputs(tmp_path, "*.json", parser=eg.make_parser("json"))
    assert sorted(d["k"] for d in out) == [1, 2]


def test_render_launcher_parses_outputs_on_close(tmp_path, monkeypatch):
    out_dir = tmp_path / "o"; out_dir.mkdir()
    (out_dir / "r.json").write_text('{"defect": "scratch"}')
    exe = tmp_path / "t.exe"; exe.write_text("x")
    monkeypatch.setattr(eg, "launch", lambda *a, **k: {"ok": True, "pid": 7, "error": None})
    monkeypatch.setattr(eg, "watch_pid", lambda pid, on_close, **k: on_close(pid))
    got = {}
    spec = {"exe_candidates": [str(exe)],
            "collect": {"dir": str(out_dir), "glob": "*.json", "parse": "json"}}
    eg.render_launcher(spec, {}, _FakeSt(click=True),
                       on_result=lambda recs: got.update(recs=recs))
    assert got["recs"] == [{"defect": "scratch"}], "declared parse:json must yield records, not paths"
