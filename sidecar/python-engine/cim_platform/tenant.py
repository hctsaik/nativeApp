"""Back-compat shim. Canonical home is core.integrations.tenant.

Kept so existing `from cim_platform.tenant import ...` sites (and the
PyInstaller hiddenimports) keep working during the restructure transition.
Remove once all imports use core.integrations.
"""

from core.integrations.tenant import (  # noqa: F401
    SystemTenant,
    load_tenant,
    load_tenant_from_file,
)
