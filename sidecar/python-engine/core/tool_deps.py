"""工具自帶相依（Per-Tool Dependencies）— 純函式核心。

對應功能 #7：工具在 `plugin.yaml` 用 `requires:` 宣告自己的 Python 相依，
框架在隔離的 per-tool venv 安裝並注入子程序的 PYTHONPATH。

設計規格見 docs/platform/per-tool-dependencies.md（§4 API、§5 安裝流程）。

本模組刻意保持**純函式、可單元測試**：
  - 不 import streamlit、不 import engine（避免循環相依與測試難度）。
  - 所有 subprocess 失敗都收斂成 DepResult(ok=False, ...)，不拋到呼叫端，
    讓 engine 端可以「單一工具相依失敗只影響該工具」。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


# ─── 常數 ──────────────────────────────────────────────────────────────────────

#: 預設 per-tool venv 家目錄（相對 engine_root）
_DEFAULT_VENVS_DIRNAME = ".tool-venvs"

#: 寫在每個 venv 內的指紋檔名（冪等判斷用）
_FINGERPRINT_FILENAME = ".cim-deps.json"

#: 環境變數名
ENV_VENVS_DIR = "CIM_TOOL_VENVS_DIR"
ENV_PYTHON = "CIM_PYTHON"
ENV_WHEELHOUSE = "CIM_WHEELHOUSE"

#: file lock 重試參數
_LOCK_RETRY_SECONDS = 30.0
_LOCK_POLL_INTERVAL = 0.1


def _is_windows() -> bool:
    """是否為 Windows 平台。

    抽成單一 helper 是為了讓測試能以隔離方式 monkeypatch 平台分支，
    而**不去污染全域 os.name / sys.platform**（污染會讓 pytest 自身的
    pathlib 行為錯亂，例如在 Windows 上把 Path 變成 PosixPath）。
    """
    return os.name == "nt" or sys.platform.startswith("win")


# ─── 結果型別 ───────────────────────────────────────────────────────────────────

@dataclass
class DepResult:
    """ensure_tool_deps 的結果。

    欄位（規格 §4）：
      ok            ── 是否成功（相依齊備或無相依）
      venv_dir      ── 該工具 venv 路徑；無相依時為 None
      site_packages ── 要注入 PYTHONPATH 的 site-packages 路徑清單
      installed     ── 本次實際安裝（或已宣告齊備）的 requires 清單
      message       ── 人類可讀訊息（成功摘要或失敗原因）
    """

    ok: bool
    venv_dir: Path | None = None
    site_packages: list[str] = field(default_factory=list)
    installed: list[str] = field(default_factory=list)
    message: str = ""


# ─── 路徑解析 ───────────────────────────────────────────────────────────────────

def _engine_root() -> Path:
    """engine 根目錄 = 本檔（core/tool_deps.py）的上一層，即 sidecar/python-engine。"""
    return Path(__file__).resolve().parents[1]


def venvs_root() -> Path:
    """per-tool venv 的家。

    預設 ``<engine_root>/.tool-venvs/``；可由環境變數 ``CIM_TOOL_VENVS_DIR``
    覆寫（packaged/frozen 模式必須指向可寫資料夾，因 exe 內建路徑唯讀）。
    """
    override = os.environ.get(ENV_VENVS_DIR)
    if override:
        return Path(override)
    return _engine_root() / _DEFAULT_VENVS_DIRNAME


def tool_venv_dir(tool_id: str) -> Path:
    """單一工具的 venv 路徑：``venvs_root() / tool_id``。"""
    return venvs_root() / tool_id


def site_packages_dirs(venv_dir: Path) -> list[str]:
    """回傳該 venv 的 site-packages 路徑清單。

    Windows: ``<venv>/Lib/site-packages``
    POSIX:   ``<venv>/lib/pythonX.Y/site-packages``（X.Y 取自 sys.version_info）
    """
    venv_dir = Path(venv_dir)
    if _is_windows():
        return [str(venv_dir / "Lib" / "site-packages")]
    pyver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    return [str(venv_dir / "lib" / pyver / "site-packages")]


def _venv_python(venv_dir: Path) -> Path:
    """venv 內的 python 直譯器路徑。"""
    venv_dir = Path(venv_dir)
    if _is_windows():
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def base_python() -> list[str]:
    """建立 venv 用的『真 Python』指令前綴。

    解析順序（規格 §4）：
      1. ``CIM_PYTHON`` 環境變數（絕對路徑）
      2. 若非 frozen：``sys.executable``
      3. frozen（``sys.frozen`` 為真）：依序嘗試 ``py -3.11`` / ``python3.11`` / ``python``

    回傳如 ``['C:/.../python.exe']`` 或 ``['py', '-3.11']``。

    注意：frozen 下的 sys.executable 是 engine.exe（無法 -m venv），故不可用。
    """
    override = os.environ.get(ENV_PYTHON)
    if override:
        return [override]

    if not getattr(sys, "frozen", False):
        return [sys.executable]

    # frozen：需要外部 real Python。回傳「首選候選」；實際可用性由
    # ensure_tool_deps 在執行 -m venv 時驗證（失敗會收斂成 DepResult.ok=False）。
    if _is_windows():
        return ["py", "-3.11"]
    return ["python3.11"]


def _frozen_python_candidates() -> list[list[str]]:
    """frozen 模式下，依序嘗試的 real Python 指令候選。"""
    if _is_windows():
        return [["py", "-3.11"], ["python3.11"], ["python"]]
    return [["python3.11"], ["python3"], ["python"]]


# ─── 指紋（冪等） ────────────────────────────────────────────────────────────────

def _requires_fingerprint(requires: list[str]) -> str:
    """以 sorted(requires) 的 JSON 算 sha256，作為冪等指紋。"""
    payload = json.dumps(sorted(requires)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _read_fingerprint(venv_dir: Path) -> str | None:
    fp_file = Path(venv_dir) / _FINGERPRINT_FILENAME
    try:
        data = json.loads(fp_file.read_text(encoding="utf-8"))
        fp = data.get("fingerprint")
        return fp if isinstance(fp, str) else None
    except (OSError, ValueError):
        return None


def _write_fingerprint(venv_dir: Path, requires: list[str]) -> None:
    fp_file = Path(venv_dir) / _FINGERPRINT_FILENAME
    payload = {
        "fingerprint": _requires_fingerprint(requires),
        "requires": sorted(requires),
    }
    # atomic：先寫 tmp 再 rename，避免半寫入的指紋檔被讀到
    tmp = fp_file.with_suffix(fp_file.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, fp_file)


# ─── file lock（避免兩程序同時建同一 venv） ─────────────────────────────────────

class _ToolLock:
    """以「獨佔建立 .lock 檔」實作的簡單跨程序 file lock。

    用 ``os.open(..., O_CREAT | O_EXCL)``：檔已存在則拋 FileExistsError，
    可在不依賴外部套件下達成跨程序互斥。逾時後強制接手（避免殘留 lock 永久卡住）。
    """

    def __init__(self, lock_path: Path):
        self._lock_path = Path(lock_path)
        self._fd: int | None = None

    def __enter__(self) -> "_ToolLock":
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + _LOCK_RETRY_SECONDS
        while True:
            try:
                self._fd = os.open(
                    str(self._lock_path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                os.write(self._fd, str(os.getpid()).encode("ascii"))
                return self
            except FileExistsError:
                if time.monotonic() >= deadline:
                    # 視為殘留鎖（持有者疑似已死），強制接手
                    try:
                        os.unlink(self._lock_path)
                    except OSError:
                        pass
                    continue
                time.sleep(_LOCK_POLL_INTERVAL)

    def __exit__(self, *exc) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        try:
            os.unlink(self._lock_path)
        except OSError:
            pass


# ─── subprocess 包裝 ────────────────────────────────────────────────────────────

def _run(cmd: list[str]) -> tuple[bool, str]:
    """執行外部指令，回 (ok, 訊息摘要)。任何例外都收斂成 (False, 訊息)。"""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, ValueError) as exc:  # 找不到直譯器、參數錯等
        return False, f"無法執行 {cmd[0]!r}：{exc}"
    if proc.returncode != 0:
        # 取 stderr 摘要（最後若干行），沒有就退回 stdout
        err = (proc.stderr or proc.stdout or "").strip()
        tail = "\n".join(err.splitlines()[-12:]) if err else f"exit code {proc.returncode}"
        return False, tail
    return True, (proc.stdout or "").strip()


# ─── 主流程 ─────────────────────────────────────────────────────────────────────

def ensure_tool_deps(
    tool_id: str,
    requires: list[str],
    *,
    wheelhouse: Path | None = None,
    base_python_cmd: list[str] | None = None,
    venv_dir: Path | None = None,
) -> DepResult:
    """確保 ``tool_id`` 的 venv 內 ``requires`` 齊備（冪等）。

    流程見規格 §5。任何失敗都回 DepResult(ok=False, message=...)，不拋例外。
    """
    requires = [r for r in (requires or []) if r and str(r).strip()]

    # ── requires 空 → 不建 venv，秒回 ─────────────────────────────────────────
    if not requires:
        return DepResult(ok=True, venv_dir=None, site_packages=[], installed=[],
                         message="無宣告相依，不建 venv。")

    target_venv = Path(venv_dir) if venv_dir is not None else tool_venv_dir(tool_id)
    wheelhouse = Path(wheelhouse) if wheelhouse is not None else _wheelhouse_from_env()

    lock_path = venvs_root() / f"{tool_id}.lock"
    try:
        with _ToolLock(lock_path):
            return _ensure_locked(tool_id, requires, target_venv, wheelhouse, base_python_cmd)
    except OSError as exc:
        return DepResult(ok=False, venv_dir=target_venv,
                         message=f"取得 venv 鎖失敗：{exc}")


def _wheelhouse_from_env() -> Path | None:
    val = os.environ.get(ENV_WHEELHOUSE)
    return Path(val) if val else None


def _ensure_locked(
    tool_id: str,
    requires: list[str],
    target_venv: Path,
    wheelhouse: Path | None,
    base_python_cmd: list[str] | None,
) -> DepResult:
    sp_dirs = site_packages_dirs(target_venv)
    venv_py = _venv_python(target_venv)

    # ── 建立 venv（若不存在）──────────────────────────────────────────────────
    if not venv_py.exists():
        ok, msg = _create_venv(target_venv, base_python_cmd)
        if not ok:
            return DepResult(ok=False, venv_dir=target_venv,
                             message=f"建立 venv 失敗：{msg}")

    # ── 指紋比對：相同則秒過（不跑 pip）─────────────────────────────────────────
    fingerprint = _requires_fingerprint(requires)
    if _read_fingerprint(target_venv) == fingerprint:
        return DepResult(ok=True, venv_dir=target_venv, site_packages=sp_dirs,
                         installed=[], message="相依已齊備（指紋命中，跳過 pip）。")

    # ── pip install ──────────────────────────────────────────────────────────
    pip_cmd = _build_pip_command(venv_py, requires, wheelhouse)
    ok, msg = _run(pip_cmd)
    if not ok:
        return DepResult(ok=False, venv_dir=target_venv, site_packages=sp_dirs,
                         message=f"pip 安裝失敗：{msg}")

    # 成功 → 寫指紋
    try:
        _write_fingerprint(target_venv, requires)
    except OSError as exc:
        # 安裝其實成功了，只是指紋沒寫成（下次會重裝，但不影響本次正確性）
        return DepResult(ok=True, venv_dir=target_venv, site_packages=sp_dirs,
                         installed=requires,
                         message=f"安裝成功，但寫入指紋失敗（下次將重跑 pip）：{exc}")

    return DepResult(ok=True, venv_dir=target_venv, site_packages=sp_dirs,
                     installed=requires, message="相依安裝完成。")


def _create_venv(target_venv: Path, base_python_cmd: list[str] | None) -> tuple[bool, str]:
    """以 real Python 建立 venv。frozen 下逐一嘗試候選直譯器。"""
    target_venv.parent.mkdir(parents=True, exist_ok=True)

    if base_python_cmd is not None:
        candidates = [list(base_python_cmd)]
    elif getattr(sys, "frozen", False):
        candidates = _frozen_python_candidates()
    else:
        candidates = [base_python()]

    last_msg = ""
    for cmd in candidates:
        ok, msg = _run([*cmd, "-m", "venv", str(target_venv)])
        if ok and _venv_python(target_venv).exists():
            return True, ""
        last_msg = msg
    hint = ""
    if getattr(sys, "frozen", False):
        hint = "（frozen 模式找不到外部 Python 3.11，請設定 CIM_PYTHON 指向真實 python.exe）"
    return False, f"{last_msg}{hint}"


def _build_pip_command(venv_py: Path, requires: list[str],
                       wheelhouse: Path | None) -> list[str]:
    """組裝 venv pip install 指令。wheelhouse 給定時走離線模式。"""
    cmd = [str(venv_py), "-m", "pip", "install"]
    if wheelhouse is not None:
        cmd += ["--no-index", f"--find-links={wheelhouse}"]
    cmd += list(requires)
    return cmd


# ─── engine 便利函式 ────────────────────────────────────────────────────────────

def pythonpath_for_tool(tool_id: str, requires: list[str]) -> str | None:
    """便利函式：ensure 後回傳要併進 PYTHONPATH 的字串（os.pathsep 串接）。

    無相依、或 ensure 失敗、或沒有 site-packages → 回 None。
    供 engine._make_env 直接使用（呼叫端負責保留既有 PYTHONPATH）。
    """
    result = ensure_tool_deps(tool_id, requires)
    if result.ok and result.site_packages:
        return os.pathsep.join(result.site_packages)
    return None
