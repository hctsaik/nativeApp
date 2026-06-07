"""Tests for core.tool_deps — per-tool dependency isolation (功能 #7)。

純單元測試：不真的連網路、不真的裝套件。
真實 subprocess（venv 建立 / pip install）一律用 monkeypatch 攔截，
僅在驗證「指令是否被組出 / 是否被呼叫」時斷言。

對應規格 docs/platform/per-tool-dependencies.md §7 全部用例。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from core import tool_deps as td
from core.tool_deps import DepResult


# ─── requires 空 → 不建 venv ────────────────────────────────────────────────────

def test_empty_requires_skips_venv():
    res = td.ensure_tool_deps("module_x", [])
    assert isinstance(res, DepResult)
    assert res.ok is True
    assert res.venv_dir is None
    assert res.installed == []
    assert res.site_packages == []


def test_blank_requires_treated_as_empty():
    # None / 空白字串都視為無相依
    assert td.ensure_tool_deps("m", None).venv_dir is None
    assert td.ensure_tool_deps("m", ["", "   "]).venv_dir is None


def test_pythonpath_for_tool_none_when_no_requires():
    assert td.pythonpath_for_tool("module_x", []) is None


# ─── ToolProcessManager: 啟動前預建 venv + 就緒 timeout（修首次啟動 500）──────────

def _make_manager(tmp_path):
    import engine  # noqa: PLC0415
    return engine.ToolProcessManager(
        tmp_path / "logs", tmp_path / "sp.json", tmp_path / "data" / "tools.sqlite"
    )


def test_prewarm_no_requires_default_timeout_and_no_install(tmp_path, monkeypatch):
    import engine  # noqa: PLC0415
    monkeypatch.setattr(engine, "_read_tool_requires", lambda m: [])
    calls = []
    monkeypatch.setattr(td, "ensure_tool_deps", lambda *a, **k: calls.append(a))
    mgr = _make_manager(tmp_path)
    assert mgr._prewarm_deps_and_timeout("module_x") == engine._TOOL_READY_TIMEOUT_DEFAULT
    assert calls == []  # no requires → never touches pip/venv


def test_prewarm_with_requires_builds_and_uses_longer_timeout(tmp_path, monkeypatch):
    import engine  # noqa: PLC0415
    monkeypatch.setattr(engine, "_read_tool_requires", lambda m: ["cowsay"])
    calls = []
    monkeypatch.setattr(td, "ensure_tool_deps",
                        lambda module, reqs, **k: calls.append((module, reqs)))
    mgr = _make_manager(tmp_path)
    assert mgr._prewarm_deps_and_timeout("module_y") == engine._TOOL_READY_TIMEOUT_WITH_DEPS
    assert calls == [("module_y", ["cowsay"])]  # venv pre-built off the readiness budget


def test_prewarm_never_raises_on_install_failure(tmp_path, monkeypatch):
    import engine  # noqa: PLC0415
    monkeypatch.setattr(engine, "_read_tool_requires", lambda m: ["cowsay"])
    def _boom(*a, **k):
        raise RuntimeError("pip exploded")
    monkeypatch.setattr(td, "ensure_tool_deps", _boom)
    mgr = _make_manager(tmp_path)
    # Dep failure must not block launch: still returns the (longer) timeout.
    assert mgr._prewarm_deps_and_timeout("module_z") == engine._TOOL_READY_TIMEOUT_WITH_DEPS


# ─── 路徑形狀 ───────────────────────────────────────────────────────────────────

def test_venvs_root_default(monkeypatch):
    monkeypatch.delenv(td.ENV_VENVS_DIR, raising=False)
    root = td.venvs_root()
    # 預設應是 <engine_root>/.tool-venvs，engine_root 即 sidecar/python-engine
    assert root.name == ".tool-venvs"
    assert root.parent.name == "python-engine"


def test_venvs_root_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv(td.ENV_VENVS_DIR, str(tmp_path / "custom-venvs"))
    assert td.venvs_root() == tmp_path / "custom-venvs"


def test_tool_venv_dir(monkeypatch, tmp_path):
    monkeypatch.setenv(td.ENV_VENVS_DIR, str(tmp_path))
    assert td.tool_venv_dir("module_042") == tmp_path / "module_042"


def test_site_packages_dirs_windows(monkeypatch):
    # patch 模組內 _is_windows helper（而非全域 os.name，避免污染 pytest 的 pathlib）
    monkeypatch.setattr(td, "_is_windows", lambda: True)
    dirs = td.site_packages_dirs(Path("C:/venvs/tool"))
    assert dirs == [str(Path("C:/venvs/tool") / "Lib" / "site-packages")]


def test_site_packages_dirs_posix(monkeypatch):
    monkeypatch.setattr(td, "_is_windows", lambda: False)
    dirs = td.site_packages_dirs(Path("/venvs/tool"))
    pyver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    assert dirs == [str(Path("/venvs/tool") / "lib" / pyver / "site-packages")]


# ─── base_python 解析順序 ───────────────────────────────────────────────────────

def test_base_python_env_override_wins(monkeypatch):
    monkeypatch.setenv(td.ENV_PYTHON, "C:/py311/python.exe")
    # 即使是 frozen，CIM_PYTHON 仍最優先
    monkeypatch.setattr(td.sys, "frozen", True, raising=False)
    assert td.base_python() == ["C:/py311/python.exe"]


def test_base_python_non_frozen_uses_sys_executable(monkeypatch):
    monkeypatch.delenv(td.ENV_PYTHON, raising=False)
    # 非 frozen：拿掉 frozen 屬性
    monkeypatch.delattr(td.sys, "frozen", raising=False)
    monkeypatch.setattr(td.sys, "executable", "/usr/bin/python3.11")
    assert td.base_python() == ["/usr/bin/python3.11"]


def test_base_python_frozen_does_not_use_sys_executable(monkeypatch):
    monkeypatch.delenv(td.ENV_PYTHON, raising=False)
    monkeypatch.setattr(td.sys, "frozen", True, raising=False)
    monkeypatch.setattr(td.sys, "executable", "C:/app/engine.exe")
    monkeypatch.setattr(td, "_is_windows", lambda: True)
    cmd = td.base_python()
    # 不可回傳 engine.exe；應為外部 real Python 候選
    assert "engine.exe" not in " ".join(cmd)
    assert cmd == ["py", "-3.11"]


def test_base_python_frozen_posix(monkeypatch):
    monkeypatch.delenv(td.ENV_PYTHON, raising=False)
    monkeypatch.setattr(td.sys, "frozen", True, raising=False)
    monkeypatch.setattr(td, "_is_windows", lambda: False)
    assert td.base_python() == ["python3.11"]


# ─── 指紋邏輯（同 requires 第二次跳過 pip）──────────────────────────────────────

class _FakeVenv:
    """攔截 subprocess：模擬 venv 建立成功 + pip 成功，並記錄被呼叫的指令。"""

    def __init__(self):
        self.calls: list[list[str]] = []
        self.created_venvs: set[str] = set()

    def run(self, cmd, **kwargs):
        self.calls.append(list(cmd))

        class _Proc:
            returncode = 0
            stdout = "ok"
            stderr = ""

        # 模擬 `-m venv <dir>`：把對應 venv python 路徑建出來，讓 _venv_python().exists() 為真
        if "venv" in cmd:
            venv_dir = Path(cmd[-1])
            self.created_venvs.add(str(venv_dir))
            py = td._venv_python(venv_dir)
            py.parent.mkdir(parents=True, exist_ok=True)
            py.write_text("# fake python", encoding="utf-8")
        return _Proc()

    @property
    def pip_calls(self):
        return [c for c in self.calls if "pip" in c]

    @property
    def venv_calls(self):
        return [c for c in self.calls if "venv" in c]


@pytest.fixture
def fake_venv(monkeypatch, tmp_path):
    monkeypatch.setenv(td.ENV_VENVS_DIR, str(tmp_path / "venvs"))
    monkeypatch.delenv(td.ENV_WHEELHOUSE, raising=False)
    monkeypatch.delenv(td.ENV_PYTHON, raising=False)
    fv = _FakeVenv()
    monkeypatch.setattr(td.subprocess, "run", fv.run)
    return fv


def test_first_install_runs_pip_and_writes_fingerprint(fake_venv):
    res = td.ensure_tool_deps("module_042", ["shapely>=2.0", "scikit-image"])
    assert res.ok is True
    assert res.venv_dir is not None
    assert res.installed == ["shapely>=2.0", "scikit-image"]
    # 第一次：venv 被建 + pip 被呼叫一次
    assert len(fake_venv.venv_calls) == 1
    assert len(fake_venv.pip_calls) == 1
    # 指紋檔已寫入
    fp_file = res.venv_dir / td._FINGERPRINT_FILENAME
    assert fp_file.exists()
    data = json.loads(fp_file.read_text(encoding="utf-8"))
    assert data["requires"] == sorted(["shapely>=2.0", "scikit-image"])


def test_second_call_same_requires_skips_pip(fake_venv):
    reqs = ["shapely>=2.0", "scikit-image"]
    first = td.ensure_tool_deps("module_042", reqs)
    assert first.ok
    pip_after_first = len(fake_venv.pip_calls)

    # 第二次：相同 requires（順序打散）→ 指紋命中，不應再跑 pip
    second = td.ensure_tool_deps("module_042", list(reversed(reqs)))
    assert second.ok is True
    assert second.installed == []  # 沒有重裝
    assert "指紋命中" in second.message or "齊備" in second.message
    assert len(fake_venv.pip_calls) == pip_after_first  # pip 呼叫次數不變


def test_changed_requires_reinstalls(fake_venv):
    td.ensure_tool_deps("module_042", ["shapely"])
    pip_count = len(fake_venv.pip_calls)
    # 改變 requires → 指紋失效 → 重新 pip
    res = td.ensure_tool_deps("module_042", ["shapely", "numpy"])
    assert res.ok
    assert len(fake_venv.pip_calls) == pip_count + 1


# ─── wheelhouse 離線模式 ────────────────────────────────────────────────────────

def test_wheelhouse_param_adds_offline_flags(fake_venv, tmp_path):
    wh = tmp_path / "wheels"
    res = td.ensure_tool_deps("module_042", ["shapely"], wheelhouse=wh)
    assert res.ok
    pip_cmd = fake_venv.pip_calls[0]
    assert "--no-index" in pip_cmd
    assert f"--find-links={wh}" in pip_cmd


def test_wheelhouse_from_env(fake_venv, monkeypatch, tmp_path):
    wh = tmp_path / "env-wheels"
    monkeypatch.setenv(td.ENV_WHEELHOUSE, str(wh))
    res = td.ensure_tool_deps("module_099", ["shapely"])
    assert res.ok
    pip_cmd = fake_venv.pip_calls[0]
    assert "--no-index" in pip_cmd
    assert f"--find-links={wh}" in pip_cmd


def test_no_wheelhouse_no_offline_flags(fake_venv):
    td.ensure_tool_deps("module_042", ["shapely"])
    pip_cmd = fake_venv.pip_calls[0]
    assert "--no-index" not in pip_cmd
    assert not any(str(a).startswith("--find-links") for a in pip_cmd)


# ─── 安裝失敗 ───────────────────────────────────────────────────────────────────

def _failing_run_factory(fail_on):
    """回傳一個 subprocess.run 替身：當指令含 fail_on 關鍵字時回非零。"""

    def _run(cmd, **kwargs):
        class _Proc:
            pass

        p = _Proc()
        if fail_on in cmd:
            p.returncode = 1
            p.stdout = ""
            p.stderr = "ERROR: Could not find a version that satisfies the requirement"
        else:
            p.returncode = 0
            p.stdout = "ok"
            p.stderr = ""
            # venv 建立成功時仍需造出 python 路徑
            if "venv" in cmd:
                py = td._venv_python(Path(cmd[-1]))
                py.parent.mkdir(parents=True, exist_ok=True)
                py.write_text("# fake", encoding="utf-8")
        return p

    return _run


def test_pip_failure_returns_not_ok(monkeypatch, tmp_path):
    monkeypatch.setenv(td.ENV_VENVS_DIR, str(tmp_path / "venvs"))
    monkeypatch.delenv(td.ENV_PYTHON, raising=False)
    monkeypatch.setattr(td.subprocess, "run", _failing_run_factory("pip"))
    res = td.ensure_tool_deps("module_042", ["nonexistent-pkg-xyz"])
    assert res.ok is False
    assert "pip 安裝失敗" in res.message
    assert "satisfies" in res.message  # stderr 摘要被帶回


def test_venv_creation_failure_returns_not_ok(monkeypatch, tmp_path):
    monkeypatch.setenv(td.ENV_VENVS_DIR, str(tmp_path / "venvs"))
    monkeypatch.delenv(td.ENV_PYTHON, raising=False)
    monkeypatch.setattr(td.subprocess, "run", _failing_run_factory("venv"))
    res = td.ensure_tool_deps("module_042", ["shapely"])
    assert res.ok is False
    assert "建立 venv 失敗" in res.message


def test_subprocess_exception_is_caught(monkeypatch, tmp_path):
    monkeypatch.setenv(td.ENV_VENVS_DIR, str(tmp_path / "venvs"))
    monkeypatch.delenv(td.ENV_PYTHON, raising=False)

    def _boom(cmd, **kwargs):
        raise OSError("python executable not found")

    monkeypatch.setattr(td.subprocess, "run", _boom)
    res = td.ensure_tool_deps("module_042", ["shapely"])
    # 例外不可拋到呼叫端
    assert res.ok is False
    assert res.message


# ─── pythonpath_for_tool 整合 ───────────────────────────────────────────────────

def test_pythonpath_for_tool_returns_site_packages(fake_venv):
    pp = td.pythonpath_for_tool("module_042", ["shapely"])
    assert pp is not None
    assert "site-packages" in pp


def test_pythonpath_for_tool_none_on_failure(monkeypatch, tmp_path):
    monkeypatch.setenv(td.ENV_VENVS_DIR, str(tmp_path / "venvs"))
    monkeypatch.delenv(td.ENV_PYTHON, raising=False)
    monkeypatch.setattr(td.subprocess, "run", _failing_run_factory("venv"))
    assert td.pythonpath_for_tool("module_042", ["shapely"]) is None


# ─── 指令組裝細節 ───────────────────────────────────────────────────────────────

def test_build_pip_command_offline():
    cmd = td._build_pip_command(Path("/v/bin/python"), ["a", "b"], Path("/wh"))
    assert cmd[:4] == [str(Path("/v/bin/python")), "-m", "pip", "install"]
    assert "--no-index" in cmd
    assert "--find-links=/wh" in cmd or f"--find-links={Path('/wh')}" in cmd
    assert cmd[-2:] == ["a", "b"]


def test_build_pip_command_online():
    cmd = td._build_pip_command(Path("/v/bin/python"), ["a"], None)
    assert "--no-index" not in cmd
    assert cmd[-1] == "a"


def test_requires_fingerprint_order_independent():
    assert td._requires_fingerprint(["a", "b"]) == td._requires_fingerprint(["b", "a"])
    assert td._requires_fingerprint(["a"]) != td._requires_fingerprint(["a", "b"])
