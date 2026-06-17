"""Tests for core.deppack — 產 wheelhouse 包 + 離線裝進 per-tool venv。

純單元測試：不真的連網、不真的 pip download。真實 subprocess 一律 monkeypatch,
僅驗證指令組裝、manifest/雜湊正確性、驗證與 fail-closed 行為,以及與 tool_deps 的接線。
對應 docs/platform/modules-independence-and-store-plan.md §6。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import deppack
from core import tool_deps as td


# ─── 指紋：deppack 與 tool_deps 共用同一演算法 ──────────────────────────────────

def test_requires_fingerprint_shared_and_order_independent():
    assert deppack.requires_fingerprint(["a", "b"]) == td.requires_fingerprint(["b", "a"])
    assert deppack.requires_fingerprint(["a"]) != deppack.requires_fingerprint(["a", "b"])
    # 與 venv 指紋(tool_deps 內部)是同一個函式
    assert deppack.requires_fingerprint is td.requires_fingerprint


# ─── manifest 型別 round-trip ───────────────────────────────────────────────────

def test_manifest_roundtrip():
    m = deppack.DepPackManifest(
        tool_id="app-lv",
        requires=["numpy", "torch==2.6.0"],
        requires_fingerprint=deppack.requires_fingerprint(["torch==2.6.0", "numpy"]),
        python_tag="cp311",
        platform_tag="win_amd64",
        wheels=[deppack.WheelEntry("torch-2.6.0-cp311-win_amd64.whl", "abc", 123)],
        created_at="2026-06-18T00:00:00Z",
    )
    back = deppack.DepPackManifest.from_json(m.to_json())
    assert back == m
    assert back.wheels[0].name.startswith("torch")


# ─── 路徑解析 ───────────────────────────────────────────────────────────────────

def test_cache_root_default(monkeypatch):
    monkeypatch.delenv(deppack.ENV_DEPPACK_CACHE, raising=False)
    root = deppack.deppack_cache_root()
    assert root.name == ".deppack-cache"
    assert root.parent.name == "python-engine"


def test_cache_root_env_override_and_tool_dirs(monkeypatch, tmp_path):
    monkeypatch.setenv(deppack.ENV_DEPPACK_CACHE, str(tmp_path / "cache"))
    assert deppack.deppack_cache_root() == tmp_path / "cache"
    assert deppack.tool_deppack_dir("app-lv") == tmp_path / "cache" / "app-lv"
    assert deppack.tool_wheelhouse_dir("app-lv") == tmp_path / "cache" / "app-lv" / "wheels"


# ─── compute_manifest / verify_wheelhouse ──────────────────────────────────────

def _write_wheel(wheels_dir: Path, name: str, data: bytes) -> None:
    wheels_dir.mkdir(parents=True, exist_ok=True)
    (wheels_dir / name).write_bytes(data)


def test_compute_manifest_hashes_and_sorts(tmp_path):
    wd = tmp_path / "wheels"
    _write_wheel(wd, "b_pkg-1.0-py3-none-any.whl", b"BBBB")
    _write_wheel(wd, "a_pkg-1.0-py3-none-any.whl", b"AAAAAA")
    m = deppack.compute_manifest("t1", ["a_pkg", "b_pkg"], wd,
                                 python_tag="cp311", platform_tag="any")
    # 依檔名排序
    assert [w.name for w in m.wheels] == [
        "a_pkg-1.0-py3-none-any.whl", "b_pkg-1.0-py3-none-any.whl"]
    import hashlib
    assert m.wheels[0].sha256 == hashlib.sha256(b"AAAAAA").hexdigest()
    assert m.wheels[0].size == 6
    assert m.requires_fingerprint == deppack.requires_fingerprint(["a_pkg", "b_pkg"])


def test_verify_ok(tmp_path):
    wd = tmp_path / "wheels"
    _write_wheel(wd, "x-1.0-py3-none-any.whl", b"hello")
    m = deppack.compute_manifest("t", ["x"], wd, python_tag="cp311", platform_tag="any")
    ok, errors = deppack.verify_wheelhouse(wd, m)
    assert ok and errors == []


def test_verify_detects_tamper(tmp_path):
    wd = tmp_path / "wheels"
    _write_wheel(wd, "x-1.0-py3-none-any.whl", b"hello")
    m = deppack.compute_manifest("t", ["x"], wd, python_tag="cp311", platform_tag="any")
    (wd / "x-1.0-py3-none-any.whl").write_bytes(b"HELLO-tampered")  # 換內容
    ok, errors = deppack.verify_wheelhouse(wd, m)
    assert not ok
    assert any("sha256" in e for e in errors)


def test_verify_detects_missing_and_extra(tmp_path):
    wd = tmp_path / "wheels"
    _write_wheel(wd, "x-1.0-py3-none-any.whl", b"hello")
    m = deppack.compute_manifest("t", ["x"], wd, python_tag="cp311", platform_tag="any")
    (wd / "x-1.0-py3-none-any.whl").unlink()                       # 缺檔
    _write_wheel(wd, "y-9.9-py3-none-any.whl", b"surprise")        # 多檔
    ok, errors = deppack.verify_wheelhouse(wd, m)
    assert not ok
    assert any("缺少" in e for e in errors)
    assert any("多餘" in e for e in errors)


# ─── build_pip_download_command 指令組裝 ─────────────────────────────────────────

def test_pip_download_command_simple():
    cmd = deppack.build_pip_download_command(["py", "-3.11"], ["numpy"], Path("/wh"),
                                             only_binary=False)
    assert cmd[:5] == ["py", "-3.11", "-m", "pip", "download"]
    assert "numpy" in cmd
    assert "-d" in cmd and str(Path("/wh")) in cmd
    assert "--only-binary=:all:" not in cmd
    assert "--platform" not in cmd


def test_pip_download_command_targeted_forces_only_binary_and_impl():
    cmd = deppack.build_pip_download_command(
        ["python"], ["torch==2.6.0"], Path("/wh"),
        platform_tag="win_amd64", python_version="3.11", abi="cp311",
        only_binary=False,  # 即使 False,指定目標標籤也應強制 only-binary
    )
    assert "--only-binary=:all:" in cmd
    assert "--platform" in cmd and "win_amd64" in cmd
    assert "--python-version" in cmd and "3.11" in cmd
    assert "--abi" in cmd and "cp311" in cmd
    assert "--implementation" in cmd and "cp" in cmd


# ─── build_wheelhouse（monkeypatch pip download）─────────────────────────────────

def test_build_wheelhouse_writes_pack_and_manifest(monkeypatch, tmp_path):
    def _fake_run(cmd):
        # 模擬 pip download：把 wheel 寫進 -d 指定的目錄
        wheels_dir = Path(cmd[cmd.index("-d") + 1])
        wheels_dir.mkdir(parents=True, exist_ok=True)
        (wheels_dir / "numpy-2.2.3-cp311-win_amd64.whl").write_bytes(b"np-wheel")
        (wheels_dir / "torch-2.6.0-cp311-win_amd64.whl").write_bytes(b"torch-wheel" * 10)
        return True, "Saved 2 files"
    monkeypatch.setattr(deppack, "_run", _fake_run)

    m = deppack.build_wheelhouse("app-lv", ["torch==2.6.0", "numpy"], tmp_path / "out",
                                 platform_tag="win_amd64", python_version="3.11", abi="cp311")
    assert m.tool_id == "app-lv"
    assert len(m.wheels) == 2
    assert m.python_tag == "cp311" and m.platform_tag == "win_amd64"
    # manifest 落地 + wheels 落地
    pack = tmp_path / "out" / "app-lv"
    assert (pack / "deppack.json").exists()
    assert (pack / "wheels" / "numpy-2.2.3-cp311-win_amd64.whl").exists()
    # 落地 manifest 可被驗證
    loaded = deppack.load_manifest(pack / "deppack.json")
    ok, errors = deppack.verify_wheelhouse(pack / "wheels", loaded)
    assert ok, errors


def test_build_wheelhouse_empty_requires_raises(tmp_path):
    with pytest.raises(ValueError):
        deppack.build_wheelhouse("t", [], tmp_path)


def test_build_wheelhouse_pip_failure_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(deppack, "_run", lambda cmd: (False, "No matching distribution"))
    with pytest.raises(deppack.DepPackError):
        deppack.build_wheelhouse("t", ["nope"], tmp_path)


# ─── verify_deppack_dir（指著資料夾判斷完不完整）────────────────────────────────

def _make_pack_dir(pack_dir: Path, tool_id: str, requires: list[str], wheels: dict[str, bytes]):
    wd = pack_dir / deppack.WHEELS_DIRNAME
    for name, data in wheels.items():
        _write_wheel(wd, name, data)
    m = deppack.compute_manifest(tool_id, requires, wd, python_tag="cp311", platform_tag="win_amd64")
    deppack.write_manifest(m, pack_dir / deppack.MANIFEST_FILENAME)
    return m


def test_verify_dir_complete(tmp_path):
    pack = tmp_path / "app-lv"
    _make_pack_dir(pack, "app-lv", ["torch"], {"torch-2.6.0.whl": b"data"})
    ok, errors = deppack.verify_deppack_dir(pack)
    assert ok and errors == []


def test_verify_dir_tampered(tmp_path):
    pack = tmp_path / "app-lv"
    _make_pack_dir(pack, "app-lv", ["torch"], {"torch-2.6.0.whl": b"data"})
    (pack / deppack.WHEELS_DIRNAME / "torch-2.6.0.whl").write_bytes(b"corrupt")
    ok, errors = deppack.verify_deppack_dir(pack)
    assert not ok and any("sha256" in e for e in errors)


def test_verify_dir_missing_wheel(tmp_path):
    pack = tmp_path / "app-lv"
    _make_pack_dir(pack, "app-lv", ["torch"], {"torch-2.6.0.whl": b"data"})
    (pack / deppack.WHEELS_DIRNAME / "torch-2.6.0.whl").unlink()
    ok, errors = deppack.verify_deppack_dir(pack)
    assert not ok and any("缺少" in e for e in errors)


def test_verify_dir_no_manifest(tmp_path):
    pack = tmp_path / "not-a-pack"
    pack.mkdir()
    ok, errors = deppack.verify_deppack_dir(pack)
    assert not ok and any("deppack.json" in e for e in errors)


# ─── prepare_tool_wheelhouse（裝置端解析 + 驗證）────────────────────────────────

def _install_pack(monkeypatch, tmp_path, tool_id, requires, wheels: dict[str, bytes]):
    cache = tmp_path / "cache"
    monkeypatch.setenv(deppack.ENV_DEPPACK_CACHE, str(cache))
    wd = deppack.tool_wheelhouse_dir(tool_id)
    for name, data in wheels.items():
        _write_wheel(wd, name, data)
    m = deppack.compute_manifest(tool_id, requires, wd, python_tag="cp311", platform_tag="win_amd64")
    deppack.write_manifest(m, deppack.tool_deppack_dir(tool_id) / deppack.MANIFEST_FILENAME)
    return cache, wd


def test_prepare_none_when_no_pack(monkeypatch, tmp_path):
    monkeypatch.setenv(deppack.ENV_DEPPACK_CACHE, str(tmp_path / "empty"))
    assert deppack.prepare_tool_wheelhouse("app-lv", ["torch"]) is None


def test_prepare_returns_wheels_dir_when_valid(monkeypatch, tmp_path):
    _, wd = _install_pack(monkeypatch, tmp_path, "app-lv", ["torch", "numpy"],
                          {"torch-2.6.0.whl": b"t", "numpy-2.2.3.whl": b"n"})
    got = deppack.prepare_tool_wheelhouse("app-lv", ["numpy", "torch"])  # 順序打散
    assert got == wd


def test_prepare_raises_on_tamper(monkeypatch, tmp_path):
    _, wd = _install_pack(monkeypatch, tmp_path, "app-lv", ["torch"], {"torch-2.6.0.whl": b"t"})
    (wd / "torch-2.6.0.whl").write_bytes(b"tampered")  # 竄改
    with pytest.raises(deppack.DepPackError):
        deppack.prepare_tool_wheelhouse("app-lv", ["torch"])


def test_prepare_raises_on_wrong_requires(monkeypatch, tmp_path):
    _install_pack(monkeypatch, tmp_path, "app-lv", ["torch"], {"torch-2.6.0.whl": b"t"})
    with pytest.raises(deppack.DepPackError):
        deppack.prepare_tool_wheelhouse("app-lv", ["torch", "numpy"])  # 指紋不符


# ─── 與 tool_deps 的接線：離線裝進 per-tool venv ────────────────────────────────

class _FakeVenv:
    """攔截 subprocess：模擬 venv 建立成功 + pip 成功,記錄指令。"""

    def __init__(self):
        self.calls: list[list[str]] = []

    def run(self, cmd, **kwargs):
        self.calls.append(list(cmd))

        class _Proc:
            returncode = 0
            stdout = "ok"
            stderr = ""

        if "venv" in cmd:
            py = td._venv_python(Path(cmd[-1]))
            py.parent.mkdir(parents=True, exist_ok=True)
            py.write_text("# fake", encoding="utf-8")
        return _Proc()

    @property
    def pip_calls(self):
        return [c for c in self.calls if "pip" in c]


def test_ensure_tool_deps_uses_deppack_offline(monkeypatch, tmp_path):
    # 安裝一個有效 dep-pack 到裝置快取
    _, wd = _install_pack(monkeypatch, tmp_path, "app-lv", ["torch"], {"torch-2.6.0.whl": b"t"})
    monkeypatch.setenv(td.ENV_VENVS_DIR, str(tmp_path / "venvs"))
    monkeypatch.delenv(td.ENV_WHEELHOUSE, raising=False)
    monkeypatch.delenv(td.ENV_PYTHON, raising=False)
    fv = _FakeVenv()
    monkeypatch.setattr(td.subprocess, "run", fv.run)

    res = td.ensure_tool_deps("app-lv", ["torch"])
    assert res.ok, res.message
    pip_cmd = fv.pip_calls[0]
    # 自動走離線：--no-index + --find-links 指向 dep-pack 的 wheels 目錄
    assert "--no-index" in pip_cmd
    assert any(str(a) == f"--find-links={wd}" for a in pip_cmd)


def test_ensure_tool_deps_fail_closed_on_tampered_deppack(monkeypatch, tmp_path):
    _, wd = _install_pack(monkeypatch, tmp_path, "app-lv", ["torch"], {"torch-2.6.0.whl": b"t"})
    (wd / "torch-2.6.0.whl").write_bytes(b"tampered")  # 竄改 → 驗證失敗
    monkeypatch.setenv(td.ENV_VENVS_DIR, str(tmp_path / "venvs"))
    monkeypatch.delenv(td.ENV_WHEELHOUSE, raising=False)
    fv = _FakeVenv()
    monkeypatch.setattr(td.subprocess, "run", fv.run)

    res = td.ensure_tool_deps("app-lv", ["torch"])
    # fail-closed：拒裝,不可退回連 PyPI
    assert res.ok is False
    assert "dep-pack" in res.message
    assert fv.pip_calls == []  # 根本沒跑 pip


def test_ensure_tool_deps_no_deppack_falls_back_online(monkeypatch, tmp_path):
    monkeypatch.setenv(deppack.ENV_DEPPACK_CACHE, str(tmp_path / "empty-cache"))
    monkeypatch.setenv(td.ENV_VENVS_DIR, str(tmp_path / "venvs"))
    monkeypatch.delenv(td.ENV_WHEELHOUSE, raising=False)
    monkeypatch.delenv(td.ENV_PYTHON, raising=False)
    fv = _FakeVenv()
    monkeypatch.setattr(td.subprocess, "run", fv.run)

    res = td.ensure_tool_deps("mod-no-pack", ["shapely"])
    assert res.ok
    pip_cmd = fv.pip_calls[0]
    assert "--no-index" not in pip_cmd  # 無 dep-pack、無 env → 線上裝
