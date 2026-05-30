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
    return sorted(_FACTORIES)


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
    if factory is None:
        raise ValueError(
            f"未知的 connector_type：{ctype!r}（可用：{', '.join(available_types())}）。"
            "請在 external_systems.yaml 設定正確的 connector_type，或註冊新的連接器工廠。")
    return factory(tenant, **opts)


# ── built-in factories (lazy) ────────────────────────────────────────────────

def _rest_factory(tenant: SystemTenant, **_opts) -> ExternalSystemConnector:
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
