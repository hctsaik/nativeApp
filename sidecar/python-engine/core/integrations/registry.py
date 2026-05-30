"""Platform-level connector registry (plugin-agnostic).

A connector is the bridge between the platform and an external system that the
declarative REST path (config/external_systems.yaml) can't express — OPC-UA,
SECS/GEM, SOAP, a vendor SDK. `scaffold connector <name>` stamps a class that
implements `core.integrations.connector.ExternalSystemConnector`; this registry
is how such a connector becomes selectable by a type name with **no edit to any
call site**.

Two ways a scaffolded connector gets registered:

  1. **Explicit** (any startup code):

        from core.integrations.registry import register_connector
        register_connector("opcua-fab", lambda tenant: OpcuaFabConnector(tenant))

  2. **Auto-discovery** (zero wiring): drop the module in
     `core/integrations/connectors/` (the scaffold default) and expose a
     module-level `register()` function; `autodiscover()` (called at engine
     startup) imports it and runs `register()`.

This lives in `core/` (not a plugin) so the scaffold template's import path is
real and stable — the R5 gap where the template pointed at a non-existent module.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Callable

# type name → factory(tenant) -> ExternalSystemConnector
_FACTORIES: dict[str, Callable[..., Any]] = {}

# Cache for autodiscover() of the default connectors dir (None = not scanned yet).
# Avoids re-importing every connector file on each build_connector/available_types.
_discovered_cache: list[str] | None = None


def register_connector(name: str, factory: Callable[..., Any]) -> None:
    """Register (or override) a connector factory under a declarative type name."""
    if not name or not str(name).strip():
        raise ValueError("connector type name 不可為空")
    _FACTORIES[str(name).strip().lower()] = factory


def is_registered(name: str) -> bool:
    return str(name).strip().lower() in _FACTORIES


def available_types() -> list[str]:
    return sorted(_FACTORIES)


def build_connector(name: str, tenant: Any = None, **opts) -> Any:
    """Construct the connector registered under `name` for a tenant."""
    factory = _FACTORIES.get(str(name).strip().lower())
    if factory is None:
        raise ValueError(
            f"未知的 connector type：{name!r}（已註冊：{', '.join(available_types()) or '無'}）。"
            "請先 register_connector(...) 或把模組放進 core/integrations/connectors/ 並提供 register()。"
        )
    return factory(tenant, **opts)


def autodiscover(connectors_dir: Path | None = None, force: bool = False) -> list[str]:
    """Import every `*.py` in `connectors_dir` and call its `register()` if present.

    Returns the module names discovered. Best-effort: a broken connector module
    is skipped (logged), never aborts startup. Default dir is
    core/integrations/connectors/ (the `scaffold connector` default destination).

    Cached: the default dir is scanned once (subsequent calls return the cached
    result without re-importing) so the labeling registry can call this on every
    connector resolution cheaply. Pass `force=True` (e.g. from POST /reload) to
    re-scan after a connector file was dropped at runtime."""
    global _discovered_cache
    use_default = connectors_dir is None
    if use_default and _discovered_cache is not None and not force:
        return list(_discovered_cache)
    base = connectors_dir or (Path(__file__).resolve().parent / "connectors")
    if not base.is_dir():
        if use_default:
            _discovered_cache = []
        return []
    import logging  # noqa: PLC0415
    discovered: list[str] = []
    for py in sorted(base.glob("*.py")):
        if py.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"_connector_{py.stem}", py)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "register") and callable(mod.register):
                mod.register()
                discovered.append(py.stem)
        except Exception as exc:  # noqa: BLE001 - one bad connector must not break startup
            # Surface the failure (the author needs to know their connector didn't
            # load) without aborting discovery of the others.
            logging.warning("connector autodiscover skipped %s: %s: %s",
                            py.name, type(exc).__name__, exc)
            continue
    if use_default:
        _discovered_cache = list(discovered)
    return discovered
