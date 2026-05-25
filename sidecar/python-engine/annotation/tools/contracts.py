from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class RuntimeStatus:
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


@dataclass
class ToolDescriptor:
    tool_id: str
    display_name: str
    default_output_format: str
    # Project mode: launch with a project directory (images/, labels/)
    supports_project_mode: bool = True
    # File mode: launch targeting a single image file
    supports_file_mode: bool = True
    aliases: list[str] = field(default_factory=list)


@runtime_checkable
class LabelingToolAdapter(Protocol):
    def detect(self, executable_override: str | None = None) -> RuntimeStatus: ...

    def launch_project(self, project_dir: Path, options: dict) -> dict: ...

    def launch_file(self, file_path: str, options: dict) -> str | None:
        """Returns error message string on failure, or None on success."""
        ...

    def get_executable(self, executable_override: str | None = None) -> str: ...
