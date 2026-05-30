from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from plugins.labeling.domain.tools.contracts import RuntimeStatus, ToolDescriptor

if TYPE_CHECKING:
    from plugins.labeling.domain.tools.registry import ToolRegistry


# ── X-AnyLabeling adapter ────────────────────────────────────────────────────


class _XAnyLabelingAdapter:
    def get_executable(self, executable_override: str | None = None) -> str:
        if executable_override and Path(executable_override).exists():
            return executable_override
        from plugins.labeling.domain.adapters.xanylabeling_runtime import detect_xanylabeling
        install = detect_xanylabeling()
        return install.executable or "xanylabeling"

    def detect(self, executable_override: str | None = None) -> RuntimeStatus:
        from plugins.labeling.domain.adapters.xanylabeling_runtime import detect_xanylabeling
        if executable_override and Path(executable_override).exists():
            from plugins.labeling.domain.adapters.xanylabeling_runtime import _read_version
            v = _read_version(executable_override)
            return RuntimeStatus(True, executable_override, v, "override", "X-AnyLabeling available.")
        inst = detect_xanylabeling()
        return RuntimeStatus(
            inst.available, inst.executable, inst.version, inst.source, inst.message
        )

    def launch_project(self, project_dir: Path, options: dict) -> dict:
        exe_override = options.get("executable_override")
        from plugins.labeling.domain.adapters.xanylabeling_runtime import launch_xanylabeling_project
        if exe_override:
            os.environ["XANYLABELING_EXE"] = exe_override
        try:
            return launch_xanylabeling_project(project_dir)
        finally:
            if exe_override:
                os.environ.pop("XANYLABELING_EXE", None)

    def launch_file(self, file_path: str, options: dict) -> str | None:
        exe_override = options.get("executable_override")
        exe = self.get_executable(exe_override)
        cmd = _wdac_safe_command(exe)
        try:
            proc = subprocess.Popen(
                cmd + ["--filename", file_path, "--output", str(Path(file_path).parent)],
                cwd=str(Path(file_path).parent),
                close_fds=True,
            )
            _ = proc.pid
            return None
        except Exception as exc:
            return str(exc)


# ── LabelMe adapter ──────────────────────────────────────────────────────────


class _LabelMeAdapter:
    def get_executable(self, executable_override: str | None = None) -> str:
        if executable_override and Path(executable_override).exists():
            return executable_override
        env_exe = os.environ.get("LABELME_EXE", "")
        if env_exe and Path(env_exe).exists():
            return env_exe
        found = shutil.which("labelme")
        return found or "labelme"

    def detect(self, executable_override: str | None = None) -> RuntimeStatus:
        exe = self.get_executable(executable_override)
        available = Path(exe).exists() or shutil.which(exe) is not None
        msg = "LabelMe is available." if available else "LabelMe was not found. Install it or set LABELME_EXE."
        return RuntimeStatus(available, exe if available else None, None, None, msg)

    def launch_project(self, project_dir: Path, options: dict) -> dict:
        exe = self.get_executable(options.get("executable_override"))
        if not (Path(exe).exists() or shutil.which(exe)):
            return {"launched": False, "command": []}
        images = project_dir / "images"
        cmd = [exe, str(images if images.exists() else project_dir)]
        subprocess.Popen(cmd, cwd=str(project_dir), close_fds=True)
        return {"launched": True, "command": cmd}

    def launch_file(self, file_path: str, options: dict) -> str | None:
        exe = self.get_executable(options.get("executable_override"))
        exe_path = Path(exe)
        # Use python -m labelme if python.exe exists alongside the exe
        if exe_path.suffix.lower() not in {"", ".py"}:
            py = exe_path.parent / "python.exe"
            if py.exists():
                cmd = [str(py), "-m", "labelme", file_path,
                       "--output", str(Path(file_path).with_suffix(".json"))]
            else:
                cmd = [exe, file_path, "--output", str(Path(file_path).with_suffix(".json"))]
        else:
            cmd = [exe, file_path, "--output", str(Path(file_path).with_suffix(".json"))]
        try:
            subprocess.Popen(cmd, close_fds=True)
            return None
        except Exception as exc:
            return str(exc)


# ── ISAT adapter ─────────────────────────────────────────────────────────────


class _IsatAdapter:
    def get_executable(self, executable_override: str | None = None) -> str:
        if executable_override and Path(executable_override).exists():
            return executable_override
        env_exe = os.environ.get("ISAT_EXE", "")
        if env_exe and Path(env_exe).exists():
            return env_exe
        scripts_dir = Path(sys.executable).parent / "Scripts"
        for name in ("isat-sam.exe", "isat-sam"):
            candidate = scripts_dir / name
            if candidate.exists():
                return str(candidate)
        return "isat-sam"

    def detect(self, executable_override: str | None = None) -> RuntimeStatus:
        exe = self.get_executable(executable_override)
        available = Path(exe).exists() or shutil.which(exe) is not None
        msg = "ISAT is available." if available else "ISAT was not found. Install isat-sam or set ISAT_EXE."
        return RuntimeStatus(available, exe if available else None, None, None, msg)

    def launch_project(self, project_dir: Path, options: dict) -> dict:
        # ISAT does not support project/file args; open GUI with cwd set
        exe = self.get_executable(options.get("executable_override"))
        if not (Path(exe).exists() or shutil.which(exe)):
            return {"launched": False, "command": []}
        cmd = [exe] if Path(exe).suffix.lower() != ".py" else [sys.executable, exe]
        subprocess.Popen(cmd, cwd=str(project_dir), close_fds=True)
        return {"launched": True, "command": cmd}

    def launch_file(self, file_path: str, options: dict) -> str | None:
        import time
        exe = self.get_executable(options.get("executable_override"))
        cmd = [exe] if Path(exe).suffix.lower() != ".py" else [sys.executable, exe]
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
                short = stderr_out[-300:] if len(stderr_out) > 300 else stderr_out
                return f"ISAT 啟動後立即結束（exit={ret}）。\n{short}"
            return None
        except Exception as exc:
            return str(exc)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _wdac_safe_command(exe: str) -> list[str]:
    """Return a command prefix that bypasses WDAC-blocked uv trampolines."""
    exe_path = Path(exe)
    if exe_path.name.lower().startswith("xanylabeling"):
        py = exe_path.parent / "python.exe"
        if py.exists():
            import site
            sp = site.getsitepackages() if hasattr(site, "getsitepackages") else []
            venv_sp = str(exe_path.parent.parent / "Lib" / "site-packages")
            insert_path = venv_sp if Path(venv_sp).exists() else (sp[0] if sp else "")
            if insert_path:
                return [
                    str(py), "-c",
                    f"import sys; sys.path.insert(0, {insert_path!r});"
                    f" from anylabeling.app import main; main()",
                ]
            return [str(py), "-m", "anylabeling.app"]
    return [exe]


# ── Registration ──────────────────────────────────────────────────────────────


def register_builtins(registry: ToolRegistry) -> None:
    registry.register(
        ToolDescriptor(
            "x-anylabeling", "X-AnyLabeling", "x-anylabeling",
            supports_project_mode=True, supports_file_mode=True,
            aliases=["xanylabeling", "x-any", "x_anylabeling"],
        ),
        _XAnyLabelingAdapter(),
    )
    registry.register(
        ToolDescriptor(
            "labelme", "LabelMe", "labelme",
            supports_project_mode=True, supports_file_mode=True,
            aliases=["label-me"],
        ),
        _LabelMeAdapter(),
    )
    registry.register(
        ToolDescriptor(
            "isat", "ISAT-SAM", "isat",
            supports_project_mode=False, supports_file_mode=True,
            aliases=["isat-sam"],
        ),
        _IsatAdapter(),
    )
