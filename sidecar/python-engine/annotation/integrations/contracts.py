"""
annotation.integrations.contracts
----------------------------------
定義外部系統連接器的共用資料結構（dataclass）與抽象介面（ABC）。

架構原則：
- 平台主動呼叫外部系統 API（Platform-Dictated）
- 外部系統只需實作 /getAntList 與 /getAntTaskDetail 兩支 endpoint
- external_context 為逃生艙欄位，平台不解析、僅透傳
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AntTask:
    """
    外部系統回傳的標注任務摘要。
    對應 GET /getAntList 回應陣列中的單一項目。

    ant_active: 0=Pending, 1=Processing, 2=Completed
    external_context: 外部系統專屬欄位（如 lot_id, eqp_id），平台透傳不解析。
    """
    ant_id: str
    ant_active: int = 0
    ant_period: str | None = None          # ISO 8601 datetime string
    external_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskDetailResponse:
    """
    POST /getAntTaskDetail 的回應。
    外部系統提供非同步 ZIP 下載連結，平台背景下載後解壓入庫。
    """
    download_url: str


@dataclass
class ConnectorHealth:
    """連接器健康檢查結果。"""
    connected: bool
    latency_ms: int | None = None
    version: str | None = None
    error: str | None = None


class ExternalSystemConnector(ABC):
    """
    外部系統連接器抽象介面。
    平台主動呼叫外部系統 API；外部系統必須遵守平台的 API 契約。
    """

    @abstractmethod
    def get_ant_list(self) -> list[AntTask]:
        """
        呼叫 GET {server_host_name}/getAntList。
        回傳外部系統中所有任務的摘要列表。
        """
        ...

    @abstractmethod
    def get_ant_task_detail(self, ant_id: str, format: str) -> TaskDetailResponse:
        """
        呼叫 POST {server_host_name}/getAntTaskDetail。
        回傳指定任務的 ZIP 非同步下載連結。

        ant_id : 外部系統的任務碼（antID）
        format : 平台要求的標注格式（如 'coco', 'yolo-detection'）
        """
        ...

    @abstractmethod
    def health_check(self) -> ConnectorHealth:
        """檢查與外部系統的連線狀態。"""
        ...
