"""Reusable launcher for external GUI programs (no-code/low-code).

The Label tool's signature capability is launching an external desktop GUI
(X-AnyLabeling), waiting for the engineer to work in it, and collecting the
results when it closes. Before this module that logic lived as ~300 hand-written
lines inside one Labeling module (`module_009/_xany_launcher.py`) and had to be
copy-pasted to build any similar tool — which is exactly the kind of thing a
semiconductor engineer needs (wrap a vendor measurement/inspection GUI, a CAD
viewer, an EDA tool…).

This module turns that pattern into a **reusable, declarative** capability. A
tool can declare an `external_gui:` block in its plugin.yaml:

    external_gui:
      exe_env: MY_TOOL_EXE                      # env var that overrides the path
      exe_candidates:                           # tried in order
        - .venv-mytool/Scripts/mytool.exe
      exe_fallback: mytool                      # bare name (resolved via PATH)
      python_module: anylabeling.app            # optional: WDAC-safe launch via
                                                #   sibling python.exe -m <module>
      args: ["--input", "{input_dir}", "--output", "{output_dir}"]
      clean_python_env: true                    # pop PYTHONPATH/HOME (default true)
      single_instance: true                     # block a 2nd concurrent launch
      collect:                                  # what to gather after it closes
        dir: "{output_dir}"
        glob: "*.json"

`{name}` placeholders in `args` / `collect.dir` are filled from the tool's
params. The hard, easy-to-get-wrong bits (env sanitization so the bundled Python
doesn't poison the child, the WDAC trampoline workaround, PID monitoring, single
-instance locking, output collection) are implemented and unit-tested here once.

The pure parts (spec validation, exe resolution, command building, env planning,
output collection) are import-light and fully testable; only `launch()` and
`watch_pid()` touch the OS. See tests/test_external_gui.py.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional


class ExternalGuiSpecError(ValueError):
    """Raised when an `external_gui:` block is malformed (surfaced to author)."""


# ── Spec validation (pure) ───────────────────────────────────────────────────


def normalize_spec(spec: Any) -> dict:
    """Validate + fill defaults for an `external_gui:` block. Pure."""
    if not isinstance(spec, dict):
        raise ExternalGuiSpecError("external_gui: 必須是物件（dict）")
    if not (spec.get("exe_env") or spec.get("exe_candidates") or spec.get("exe_fallback")):
        raise ExternalGuiSpecError(
            "external_gui 需要至少一個 exe 來源：exe_env / exe_candidates / exe_fallback"
        )
    args = spec.get("args", [])
    if not isinstance(args, list):
        raise ExternalGuiSpecError("external_gui.args 必須是清單（list）")
    collect = spec.get("collect")
    if collect is not None:
        if not isinstance(collect, dict) or not collect.get("dir"):
            raise ExternalGuiSpecError("external_gui.collect 需要 'dir'（要掃描的輸出資料夾）")
        parse = collect.get("parse")
        if parse is not None and parse not in _PARSERS:
            raise ExternalGuiSpecError(
                f"external_gui.collect.parse '{parse}' 不支援；可用：{sorted(_PARSERS)}"
            )
    return {
        "exe_env": spec.get("exe_env"),
        "exe_candidates": list(spec.get("exe_candidates", [])),
        "exe_fallback": spec.get("exe_fallback", ""),
        "python_module": spec.get("python_module"),
        "args": args,
        "clean_python_env": spec.get("clean_python_env", True),
        "prepend_exe_dir": spec.get("prepend_exe_dir", True),
        "single_instance": spec.get("single_instance", True),
        "collect": (
            {"dir": collect["dir"], "glob": collect.get("glob", "*"),
             "parse": collect.get("parse")}
            if collect else None
        ),
        "button_label": spec.get("button_label", "▶ 啟動外部工具"),
    }


# ── Exe resolution / command / env (pure) ────────────────────────────────────


def resolve_exe(exe_env: Optional[str] = None,
                exe_candidates: tuple[str, ...] | list[str] = (),
                exe_fallback: str = "",
                root: Path | None = None) -> str:
    """Resolve the external exe path. Order: env var → candidates → fallback.

    Relative candidates resolve against `root` (default: the engine dir)."""
    base = root or Path(__file__).resolve().parents[1]
    cands: list[Path] = []
    if exe_env and os.environ.get(exe_env):
        cands.append(Path(os.environ[exe_env]))
    for c in exe_candidates:
        p = Path(c)
        cands.append(p if p.is_absolute() else base / p)
    for c in cands:
        if str(c) and c.exists():
            return str(c)
    return exe_fallback


def command_prefix(exe: str, python_module: Optional[str] = None) -> list[str]:
    """Build the launch command prefix.

    When `python_module` is given and a sibling python interpreter exists next to
    the exe, launch via `<python> -m <module>` instead of the exe directly. This
    is the WDAC / uv-trampoline workaround the Label tool needs (running the
    .exe trampoline can be blocked by Windows Application Control)."""
    p = Path(exe)
    if python_module:
        py = p.parent / ("python.exe" if os.name == "nt" else "python")
        if py.exists():
            return [str(py), "-m", python_module]
    return [exe]


def interpolate_args(args: list, params: dict) -> list[str]:
    """Fill `{name}` placeholders in args from params. Raises on unknown key."""
    out: list[str] = []
    for a in args:
        if isinstance(a, str):
            try:
                out.append(a.format(**params))
            except KeyError as exc:
                raise ExternalGuiSpecError(
                    f"external_gui.args 參照了未知參數 {exc}（可用：{sorted(params)}）"
                ) from exc
        else:
            out.append(str(a))
    return out


def plan_env(exe: str, clean_python_env: bool = True,
             prepend_exe_dir: bool = True,
             base_env: dict | None = None) -> dict[str, str]:
    """Plan the child process environment. Pure (does not read os.environ unless
    base_env is None — pass base_env in tests for determinism).

    `clean_python_env` removes PYTHONPATH/PYTHONHOME and sets PYTHONNOUSERSITE so
    a child Python app does not inherit our (possibly frozen) interpreter's
    module search path — the single most common reason a launched Python GUI
    fails to start."""
    env = dict(base_env if base_env is not None else os.environ)
    if clean_python_env:
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        env["PYTHONNOUSERSITE"] = "1"
    if prepend_exe_dir:
        p = Path(exe)
        if p.parent and (p.exists() or os.sep in exe):
            env["PATH"] = str(p.resolve().parent) + os.pathsep + env.get("PATH", "")
    return env


def build_launch(spec: dict, params: dict, root: Path | None = None) -> dict:
    """Combine resolution + command + env into a launch plan (pure). Returns
    {"exe", "cmd", "env"} ready for launch()."""
    spec = normalize_spec(spec)
    exe = resolve_exe(spec["exe_env"], spec["exe_candidates"],
                      spec["exe_fallback"], root=root)
    if not exe:
        raise ExternalGuiSpecError("找不到外部程式（exe）；請設定 exe_env 或安裝後重試")
    cmd = command_prefix(exe, spec["python_module"]) + interpolate_args(spec["args"], params)
    env = plan_env(exe, spec["clean_python_env"], spec["prepend_exe_dir"])
    return {"exe": exe, "cmd": cmd, "env": env}


# ── Output collection (pure-ish: touches filesystem only) ─────────────────────


def _parse_json(f: Path) -> Any:
    import json  # noqa: PLC0415
    return json.loads(f.read_text(encoding="utf-8"))


def _parse_lines(f: Path) -> list[str]:
    return f.read_text(encoding="utf-8").splitlines()


def _parse_text(f: Path) -> str:
    return f.read_text(encoding="utf-8")


def _parse_csv(f: Path) -> list[dict]:
    import csv  # noqa: PLC0415
    return list(csv.DictReader(f.read_text(encoding="utf-8").splitlines()))


_PARSERS: dict[str, Callable[[Path], Any]] = {
    "json": _parse_json, "lines": _parse_lines, "text": _parse_text, "csv": _parse_csv,
}


def make_parser(parse: Optional[str]) -> Callable[[Path], Any] | None:
    """Map a declarative `collect.parse` type to a parser callable (or None →
    return file paths). Lets a no-code tool turn output files into usable records
    (json/csv/lines/text) without writing any Python."""
    if not parse:
        return None
    return _PARSERS[parse]


def collect_outputs(output_dir: str | Path, glob: str = "*",
                    parser: Callable[[Path], Any] | None = None) -> list:
    """After the external GUI closes, scan `output_dir` for files matching `glob`
    and (optionally) parse each. A failing parser on one file is skipped, never
    aborts the whole collection."""
    d = Path(output_dir)
    if not d.is_dir():
        return []
    results: list = []
    for f in sorted(d.glob(glob)):
        if parser is None:
            results.append(str(f))
            continue
        try:
            results.append(parser(f))
        except Exception:
            pass
    return results


# ── OS adapters (thin) ────────────────────────────────────────────────────────

# single-instance bookkeeping (process-local; pair with a DB lock for cross-proc)
_running: dict[str, int] = {}
_monitors: dict[int, threading.Thread] = {}


def launch(cmd: list[str], env: dict | None = None,
           cwd: str | Path | None = None, key: str | None = None,
           single_instance: bool = False) -> dict:
    """Start the external program. Returns {"ok", "pid", "error"}.

    When `single_instance` is set and a live process is already tracked under
    `key`, the launch is refused (mirrors the Label tool's lock)."""
    if single_instance and key:
        prev = _running.get(key)
        if prev is not None and _pid_alive(prev):
            return {"ok": False, "pid": None, "error": f"已有一個執行中的程序（pid={prev}）"}
    try:
        proc = subprocess.Popen(cmd, env=env, cwd=str(cwd) if cwd else None)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "pid": None, "error": str(exc)}
    if key:
        _running[key] = proc.pid
    return {"ok": True, "pid": proc.pid, "error": None}


def _pid_alive(pid: int) -> bool:
    try:
        import psutil  # noqa: PLC0415
        return psutil.pid_exists(pid)
    except Exception:
        # Fallback: os.kill(pid, 0) on POSIX; assume alive on failure
        if os.name == "posix":
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False
        return True


def watch_pid(pid: int, on_close: Callable[[int], None], interval: float = 2.0) -> threading.Thread:
    """Poll until `pid` exits, then call on_close(pid) once. Daemon thread."""
    def _run() -> None:
        while True:
            time.sleep(interval)
            if not _pid_alive(pid):
                try:
                    on_close(pid)
                finally:
                    _running_pop_pid(pid)
                break
    t = threading.Thread(target=_run, daemon=True, name=f"extgui-monitor-{pid}")
    t.start()
    _monitors[pid] = t
    return t


def _running_pop_pid(pid: int) -> None:
    for k, v in list(_running.items()):
        if v == pid:
            _running.pop(k, None)


def resolve_collect_dir(norm_spec: dict, params: dict) -> Optional[str]:
    """Interpolate the collect.dir for a normalized spec (pure). None if no
    collect block."""
    collect = norm_spec.get("collect")
    if not collect:
        return None
    try:
        return str(collect["dir"]).format(**params)
    except KeyError as exc:
        raise ExternalGuiSpecError(
            f"external_gui.collect.dir 參照了未知參數 {exc}"
        ) from exc


def render_launcher(spec: Any, params: dict, st: Any, root: Path | None = None,
                    key: str = "external_gui",
                    on_result: Callable[[list], None] | None = None,
                    dry_run_preview: bool = True) -> dict:
    """Streamlit adapter: render a launch button for a declarative `external_gui:`
    block. `st` is injected for testability.

    When `on_result` is given and the spec declares a `collect:` block, the
    launcher watches the launched process and — once it closes — gathers the
    output files (core.collect_outputs) and calls on_result(files). This is what
    makes the no-code path equivalent to the Label tool's full
    launch→work→close→recover loop (not just "launch").

    `dry_run_preview` shows the exact resolved exe/command BEFORE launching, so
    a missing exe or wrong arg is visible without starting anything."""
    norm = normalize_spec(spec)

    # Pre-flight preview: resolve and show the command without launching.
    if dry_run_preview:
        try:
            plan = build_launch(spec, params, root=root)
            with st.expander("預覽將執行的命令（不會啟動）", expanded=False):
                st.write(f"程式：{plan['exe']}")
                st.code(" ".join(plan["cmd"]))
        except ExternalGuiSpecError as exc:
            st.warning(f"尚未就緒：{exc}")

    if st.button(norm["button_label"], type="primary", key=f"{key}_launch"):
        try:
            plan = build_launch(spec, params, root=root)
        except ExternalGuiSpecError as exc:
            st.error(str(exc))
            return {"ok": False, "error": str(exc)}
        res = launch(plan["cmd"], env=plan["env"], key=key,
                     single_instance=norm["single_instance"])
        if res["ok"]:
            st.success(f"已啟動外部工具（pid={res['pid']}）。完成後關閉該視窗即可自動回收結果。")
            if on_result is not None and norm.get("collect"):
                cdir = resolve_collect_dir(norm, params)
                cglob = norm["collect"]["glob"]

                cparser = make_parser(norm["collect"].get("parse"))

                def _on_close(_pid: int, _dir=cdir, _glob=cglob, _p=cparser) -> None:
                    on_result(collect_outputs(_dir, _glob, parser=_p))

                watch_pid(res["pid"], _on_close)
        else:
            st.error(f"啟動失敗：{res['error']}")
        return res
    return {"ok": None, "error": None}
