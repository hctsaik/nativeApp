from __future__ import annotations

from plugins.labeling.domain.formats.contracts import FormatAdapter, FormatDescriptor


class FormatRegistry:
    def __init__(self) -> None:
        self._descriptors: dict[str, FormatDescriptor] = {}
        self._adapters: dict[str, FormatAdapter] = {}
        self._aliases: dict[str, str] = {}

    def register(self, descriptor: FormatDescriptor, adapter: FormatAdapter) -> None:
        fid = descriptor.format_id
        self._descriptors[fid] = descriptor
        self._adapters[fid] = adapter
        self._aliases[fid] = fid
        for alias in descriptor.aliases:
            self._aliases[alias] = fid

    def normalize(self, format_id: str) -> str:
        fmt = (format_id or "").strip().lower().replace("_", "-")
        return self._aliases.get(fmt, fmt)

    def get(self, format_id: str) -> tuple[FormatDescriptor, FormatAdapter]:
        canonical = self.normalize(format_id)
        desc = self._descriptors.get(canonical)
        if desc is None:
            raise ValueError(f"Unsupported annotation format: {format_id!r}")
        return desc, self._adapters[canonical]

    def list_supported(self) -> list[dict]:
        return [
            {
                "id": desc.format_id,
                "name": desc.display_name,
                "can_import": desc.capabilities.can_import,
                "can_export": desc.capabilities.can_export,
            }
            for desc in self._descriptors.values()
        ]


_registry: FormatRegistry | None = None


def get_format_registry() -> FormatRegistry:
    global _registry
    if _registry is None:
        from plugins.labeling.domain.formats.builtins import register_builtins
        _registry = FormatRegistry()
        register_builtins(_registry)
    return _registry


def reset_format_registry() -> None:
    """Reset singleton — for use in tests only."""
    global _registry
    _registry = None
