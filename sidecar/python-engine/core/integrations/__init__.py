"""Platform-level external-system integration contracts (domain-agnostic)."""

from core.integrations.connector import (
    ConnectorHealth,
    ExternalSystemConnector,
    ExternalTask,
    ExternalTaskDetail,
)
from core.integrations.tenant import (
    SystemTenant,
    load_tenant,
    load_tenant_from_file,
)

__all__ = [
    "ConnectorHealth",
    "ExternalSystemConnector",
    "ExternalTask",
    "ExternalTaskDetail",
    "SystemTenant",
    "load_tenant",
    "load_tenant_from_file",
]
