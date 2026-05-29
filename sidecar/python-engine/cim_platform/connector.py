"""Back-compat shim. Canonical home is core.integrations.connector.

Kept so existing `from cim_platform.connector import ...` sites (and the
PyInstaller hiddenimports) keep working during the restructure transition.
Remove once all imports use core.integrations.
"""

from core.integrations.connector import (  # noqa: F401
    ConnectorHealth,
    ExternalSystemConnector,
    ExternalTask,
    ExternalTaskDetail,
)
