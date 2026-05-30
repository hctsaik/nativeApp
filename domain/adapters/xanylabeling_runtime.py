from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class XAnyLabelingInstall:
    available: bool
    executable: str | None = None
    version: str | None = None
    source: str | None = None
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "executable": self.executable,
            "version": self.version,
            "source": self.source,
            "message": self.message,
        }


def detect_xanylabeling() -> XAnyLabelingInstall:
    candidates = _candidate_executables()
    for source, executable in candidates:
        if executable and Path(executable).exists():
            version = _read_version(executable)
            return XAnyLabelingInstall(
                available=True,
                executable=str(Path(executable)),
                version=version,
                source=source,
                message="X-AnyLabeling is available.",
            )
    which = shutil.which("xanylabeling")
    if which:
        return XAnyLabelingInstall(
            available=True,
            executable=which,
            version=_read_version(which),
            source="PATH",
            message="X-AnyLabeling is available from PATH.",
        )
    return XAnyLabelingInstall(
        available=False,
        message="X-AnyLabeling was not found. Install it or set XANYLABELING_EXE.",
    )


def launch_xanylabeling_project(project_dir: Path | str) -> dict:
    install = detect_xanylabeling()
    if not install.available or not install.executable:
        return {"launched": False, "install": install.to_dict(), "command": []}
    project = Path(project_dir)
    images_dir = project / "images"
    labels_dir = project / "labels"
    classes_path = project / "classes.txt"
    work_dir = project / ".xanylabeling"
    work_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    command = _command_prefix(install.executable) + [
        "--filename",
        str(images_dir if images_dir.exists() else project),
        "--output",
        str(labels_dir),
        "--work-dir",
        str(work_dir),
        "--nodata",
        "--autosave",
        "--no-auto-update-check",
    ]
    if classes_path.exists():
        command.extend(["--labels", str(classes_path), "--validatelabel", "exact"])

    subprocess.Popen(
        command,
        cwd=str(project),
        env=_subprocess_env(install.executable),
        close_fds=True,
    )
    return {"launched": True, "install": install.to_dict(), "command": command}


def _candidate_executables() -> list[tuple[str, str | None]]:
    repo_root = Path(__file__).resolve().parents[4]
    env_exe = os.environ.get("XANYLABELING_EXE")
    return [
        ("XANYLABELING_EXE", env_exe),
        (
            "repo .venv-xanylabeling",
            str(repo_root / ".venv-xanylabeling" / "Scripts" / "xanylabeling.exe"),
        ),
    ]


def _subprocess_env(executable: str | None) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONNOUSERSITE"] = "1"
    if executable:
        scripts_dir = str(Path(executable).resolve().parent)
        env["PATH"] = scripts_dir + os.pathsep + env.get("PATH", "")
    return env


def _command_prefix(executable: str | None) -> list[str]:
    if not executable:
        return ["xanylabeling"]
    exe = Path(executable)
    if exe.name.lower().startswith("xanylabeling"):
        python = exe.parent / "python.exe"
        if python.exists():
            return [str(python), "-m", "anylabeling.app"]
    return [str(exe)]


def _read_version(executable: str) -> str | None:
    try:
        completed = subprocess.run(
            [executable, "version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception:
        return None
    text = (completed.stdout or completed.stderr).strip()
    return text.splitlines()[-1].strip() if text else None
