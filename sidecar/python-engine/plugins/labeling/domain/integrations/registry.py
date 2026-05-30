"""Declarative connector factory/registry (labeling view of the platform registry).

A connector is selected declaratively:

  1. explicit `tenant.connector_type` (set from external_systems.yaml
     `connector_type:`) wins;
  2. otherwise it is inferred from the `server_host_name` URL scheme
     (`fake://`→fake, `file://`→file, `http(s)://`→rest).

**Single source of truth**: connector factories live in the platform-level
`core.integrations.registry`. This module owns only the labeling-specific URL
inference (`infer_type`) and the built-in rest/file/fake factories, which it
registers INTO core (labeling → core is the allowed dependency direction; core
never imports labeling). `_FACTORIES` is an alias of core's dict, so there is
exactly one store — `register_connector`/`build_connector`/`available_types`
all operate on it, and scaffolded non-REST connectors (autodiscovered by core)
are reachable here automatically.
"""

from __future__ import annotations

from typing import Callable
from urllib.parse import urlparse

from core.integrations import registry as _core
from plugins.labeling.domain.core.models import SystemTenant
from plugins.labeling.domain.integrations.contracts import ExternalSystemConnector

# Alias the platform registry's factory dict — single shared store (no second
# dict). Tests that touch `registry._FACTORIES` therefore see the real store.
_FACTORIES: dict[str, Callable[..., ExternalSystemConnector]] = _core._FACTORIES


def register_connector(name: str, factory: Callable[..., ExternalSystemConnector]) -> None:
    """Register (or override) a connector factory (delegates to the core store)."""
    _core.register_connector(name, factory)


def _ensure_builtins() -> None:
    """Register labeling's rest/file/fake factories into the core store (idempotent)
    and pick up any scaffolded non-REST connectors (cached autodiscover)."""
    for name, factory in (("rest", _rest_factory), ("file", _file_factory), ("fake", _fake_factory)):
        if not _core.is_registered(name):
            _core.register_connector(name, factory)
    _core.autodiscover()


def available_types() -> list[str]:
    _ensure_builtins()
    return _core.available_types()


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
    if not _core.is_registered(ctype):
        raise ValueError(
            f"未知的 connector_type：{ctype!r}（可用：{', '.join(available_types())}）。"
            "請在 external_systems.yaml 設定正確的 connector_type，或用 "
            "`python tools/scaffold.py connector <name>` 產生連接器（放 core/integrations/connectors/）。")
    return _core.build_connector(ctype, tenant, **opts)


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
