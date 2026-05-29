"""
annotation.integrations.profiles
----------------------------------
向下相容的 re-export 層。

SystemTenant 與載入函式已移至 platform.tenant；此模組保留舊名稱以免破壞現有 import。
新程式碼請直接從 platform.tenant 匯入。
"""
from __future__ import annotations

from core.integrations.tenant import (
    SystemTenant,
    load_tenant as load_profile,
    load_tenant_from_file as load_profile_from_file,
)

__all__ = [
    "SystemTenant",
    "load_profile",
    "load_profile_from_file",
]
