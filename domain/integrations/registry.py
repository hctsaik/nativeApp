"""Declarative connector factory/registry.

Adding a new external-system protocol used to require editing the hard-coded
if/else in `services._get_connector`. Now a connector is selected declaratively:

  1. explicit `tenant.connector_type` (set from external_systems.yaml
     `connector_type:`) wins;
  2. otherwise it is inferred from the `server_host_name` URL scheme
     (`fake://`→fake, `file://`→file, `http(s)://`→rest).

A brand-new protocol only needs `register_connector("sql", factory)` (one line),
no change to call sites. Built-ins (rest/file/fake) are registered lazily so the
heavier connector modules are imported only when actually used.
"""

from __future__ import annotations

from typing import Callable
from urllib.parse import urlparse

from plugins.labeling.domain.core.models import SystemTenant
from plugins.labeling.domain.integrations.contracts import ExternalSystemConnector

# name → factory(tenant, **opts) -> ExternalSystemConnector
_FACTORIES: dict[str, Callable[..., ExternalSystemConnector]] = {}


def register_connector(name: str, factory: Callable[..., ExternalSystemConnector]) -> None:
    """Register (or override) a connector factory under a declarative type name."""
    _FACTORIES[name.strip().lower()] = factory


def available_types() -> list[str]:
    _ensure_builtins()
    # Merge in platform-level connectors (scaffolded non-REST connectors that
    # auto-registered via core.integrations.registry.autodiscover) so the
    # Management Center connector_type dropdown also lists them.
    types = set(_FACTORIES)
    try:
        from core.integrations import registry as _core_registry  # noqa: PLC0415
        _core_registry.autodiscover()
        types.update(_core_registry.available_types())
    except Exception:
        pass
    return sorted(types)


def infer_type(server_host_name: str) -> str:
    """Map a host URL scheme to a built-in connector type (defaults to rest)."""
    scheme = (urlparse(server_host_name or "").scheme or "").lower()
    if scheme == "fake":
        return "fake"
    if scheme == "file":
        return "file"
    return "rest"


def build_connector(tenant: SystemTenant, **opts) -> ExternalSystemConnector:
    """Resolve + construct the connector for a tenant (declarative type → factory)."""
    _ensure_builtins()
    ctype = (getattr(tenant, "connector_type", None) or "").strip().lower() \
        or infer_type(tenant.server_host_name)
    factory = _FACTORIES.get(ctype)
    if factory is not None:
        return factory(tenant, **opts)
    # Not a labeling built-in → delegate to the platform-level registry, which
    # holds non-REST connectors scaffolded via `scaffold connector` and
    # auto-registered by core.integrations.registry.autodiscover(). This is the
    # single bridge that makes a scaffolded connector reachable by the live
    # task-claim path (labeling → core is the allowed dependency direction).
    try:
        from core.integrations import registry as _core_registry  # noqa: PLC0415
        _core_registry.autodiscover()
        if _core_registry.is_registered(ctype):
            return _core_registry.build_connector(ctype, tenant, **opts)
    except Exception as exc:  # noqa: BLE001
        import logging  # noqa: PLC0415
        logging.warning("core connector registry delegation failed for %r: %s", ctype, exc)
    raise ValueError(
        f"未知的 connector_type：{ctype!r}（可用：{', '.join(available_types())}）。"
        "請在 external_systems.yaml 設定正確的 connector_type，或用 "
        "`python tools/scaffold.py connector <name>` 產生連接器（放 core/integrations/connectors/）。")


# ── built-in factories (lazy) ────────────────────────────────────────────────

def _rest_factory(tenant: SystemTenant, **_opts) -> ExternalSystemConnector:
    # Declarative REST variant: if the tenant carries an endpoint/field mapping,
    # use the configurable connector so a new REST system needs no new class.
    if getattr(tenant, "connector_config", None):
        from plugins.labeling.domain.integrations.connectors.configurable_rest_connector import (
            ConfigurableRestConnector,
        )
        return ConfigurableRestConnector(tenant)
    from plugins.labeling.domain.integrations.connectors.rest_connector import RestConnector
    return RestConnector(tenant)


def _file_factory(tenant: SystemTenant, **_opts) -> ExternalSystemConnector:
    from plugins.labeling.domain.integrations.connectors.file_connector import FileConnector
    return FileConnector(tenant)


def _fake_factory(tenant: SystemTenant, **_opts) -> ExternalSystemConnector:
    from plugins.labeling.domain.integrations.connectors.fake_connector import FakeConnector
    tasks = [
        {"antID": f"FAKE_TASK_{i:03d}", "antActive": 0,
         "antPeriod": "2026-05-26T08:00:00Z",
         "external_context": {"lot_id": f"L{i:02d}", "eqp_id": "AOI-01"}}
        for i in range(1, 4)
    ]
    return FakeConnector(tasks=tasks, download_url="")


def _ensure_builtins() -> None:
    if not _FACTORIES:
        register_connector("rest", _rest_factory)
        register_connector("file", _file_factory)
        register_connector("fake", _fake_factory)
