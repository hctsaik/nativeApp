"""
annotation.integrations.contracts
----------------------------------
向下相容的 re-export 層。

通用介面已移至 platform.connector；此模組保留舊名稱以免破壞現有 import。
新程式碼請直接從 platform.connector 匯入。

舊名稱對應關係：
  AntTask            → platform.connector.ExternalTask
  TaskDetailResponse → platform.connector.ExternalTaskDetail
  ConnectorHealth    → platform.connector.ConnectorHealth（同名）
  ExternalSystemConnector → platform.connector.ExternalSystemConnector（同名）
"""
from __future__ import annotations

from core.integrations.connector import (
    ConnectorHealth,
    ExternalSystemConnector,
    ExternalTask as AntTask,
    ExternalTaskDetail as TaskDetailResponse,
)

__all__ = [
    "AntTask",
    "TaskDetailResponse",
    "ConnectorHealth",
    "ExternalSystemConnector",
]
