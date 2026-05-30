from __future__ import annotations

from plugins.labeling.domain.tools.contracts import LabelingToolAdapter, ToolDescriptor


class ToolRegistry:
    def __init__(self) -> None:
        self._descriptors: dict[str, ToolDescriptor] = {}
        self._adapters: dict[str, LabelingToolAdapter] = {}
        self._aliases: dict[str, str] = {}

    def register(self, descriptor: ToolDescriptor, adapter: LabelingToolAdapter) -> None:
        tid = descriptor.tool_id
        self._descriptors[tid] = descriptor
        self._adapters[tid] = adapter
        self._aliases[tid] = tid
        for alias in descriptor.aliases:
            self._aliases[alias] = tid

    def normalize(self, tool_id: str) -> str:
        tool = (tool_id or "").strip().lower().replace("_", "-")
        return self._aliases.get(tool, tool)

    def get(self, tool_id: str) -> tuple[ToolDescriptor, LabelingToolAdapter]:
        canonical = self.normalize(tool_id)
        desc = self._descriptors.get(canonical)
        if desc is None:
            raise ValueError(f"Unsupported labeling tool: {tool_id!r}")
        return desc, self._adapters[canonical]

    def list_supported(self) -> list[dict]:
        return [
            {
                "id": desc.tool_id,
                "name": desc.display_name,
                "default_output_format": desc.default_output_format,
                "supports_project_mode": desc.supports_project_mode,
                "supports_file_mode": desc.supports_file_mode,
            }
            for desc in self._descriptors.values()
        ]


_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        from plugins.labeling.domain.tools.builtins import register_builtins
        _registry = ToolRegistry()
        register_builtins(_registry)
    return _registry


def reset_tool_registry() -> None:
    """Reset singleton — for use in tests only."""
    global _registry
    _registry = None
