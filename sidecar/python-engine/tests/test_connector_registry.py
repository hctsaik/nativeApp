"""Declarative connector factory/registry (no-code protocol selection)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plugins.labeling.domain.core.models import SystemTenant
from plugins.labeling.domain.integrations import registry


def _tenant(host: str, ctype: str | None = None) -> SystemTenant:
    return SystemTenant(
        tenant_id="t1", system_name="sys", server_host_name=host,
        target_format="xanylabeling", connector_type=ctype)


def test_infer_type_from_scheme():
    assert registry.infer_type("fake://x") == "fake"
    assert registry.infer_type("file:///data") == "file"
    assert registry.infer_type("http://h:8765") == "rest"
    assert registry.infer_type("https://h") == "rest"
    assert registry.infer_type("") == "rest"


def test_build_connector_infers_fake_and_rest():
    fake = registry.build_connector(_tenant("fake://demo"))
    assert type(fake).__name__ == "FakeConnector"
    rest = registry.build_connector(_tenant("http://localhost:8765"))
    assert type(rest).__name__ == "RestConnector"


def test_explicit_connector_type_overrides_scheme():
    # host looks like REST but connector_type forces file
    c = registry.build_connector(_tenant("http://localhost:8765", ctype="file"))
    assert type(c).__name__ == "FileConnector"


def test_register_new_protocol_no_callsite_change():
    """A brand-new protocol only needs register_connector(), not editing services."""
    class _SqlConnector:  # stand-in
        def __init__(self, tenant, **_):
            self.tenant = tenant

    registry.register_connector("sql", lambda tenant, **o: _SqlConnector(tenant, **o))
    try:
        c = registry.build_connector(_tenant("sql://db", ctype="sql"))
        assert isinstance(c, _SqlConnector)
        assert "sql" in registry.available_types()
    finally:
        registry._FACTORIES.pop("sql", None)


def test_unknown_connector_type_raises_actionable():
    with pytest.raises(ValueError, match="connector_type"):
        registry.build_connector(_tenant("x://y", ctype="grpc-nonexistent"))
