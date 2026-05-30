from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from plugins.labeling.domain.adapters.xanylabeling_runtime import detect_xanylabeling, launch_xanylabeling_project


@dataclass(slots=True)
class LabelingToolInstall:
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


def detect_labeling_tool(tool: str) -> LabelingToolInstall:
    normalized = _normalize_tool(tool)
    if normalized == "x-anylabeling":
        detected = detect_xanylabeling().to_dict()
        return LabelingToolInstall(**detected)
    if normalized == "labelme":
        return _detect_executable("LabelMe", "LABELME_EXE", "labelme")
    if normalized == "isat":
        return _detect_executable("ISAT", "ISAT_EXE", "isat-sam")
    return LabelingToolInstall(False, message=f"Unsupported labeling tool: {tool}")


def launch_labeling_project(tool: str, project_dir: Path | str) -> dict:
    normalized = _normalize_tool(tool)
    project = Path(project_dir)
    if normalized == "x-anylabeling":
        return launch_xanylabeling_project(project)
    install = detect_labeling_tool(normalized)
    if not install.available or not install.executable:
        return {"launched": False, "install": install.to_dict(), "command": []}
    command = [install.executable]
    if normalized == "labelme":
        images = project / "images"
        command.extend([str(images if images.exists() else project)])
    # ISAT's current console script opens the GUI without documented project args.
    subprocess.Popen(command, cwd=str(project), close_fds=True)
    return {"launched": True, "install": install.to_dict(), "command": command}


def _detect_executable(display_name: str, env_var: str, command_name: str) -> LabelingToolInstall:
    env_exe = os.environ.get(env_var, "")
    if env_exe and Path(env_exe).exists():
        return LabelingToolInstall(True, env_exe, source=env_var, message=f"{display_name} is available.")
    found = shutil.which(command_name)
    if found:
        return LabelingToolInstall(True, found, source="PATH", message=f"{display_name} is available from PATH.")
    return LabelingToolInstall(False, message=f"{display_name} was not found. Install it or set {env_var}.")


def _normalize_tool(value: str) -> str:
    tool = (value or "").strip().lower().replace("_", "-")
    if tool == "xanylabeling":
        return "x-anylabeling"
    return tool

