"""
platform.connector
------------------
通用外部系統連接器抽象介面。

這一層定義「平台如何與外部系統對話」的契約，與具體的業務領域（如 annotation）無關。
任何需要對接外部任務系統的功能模組（Annotation、BI、QC...）都可以實作這個介面。

架構原則：
- Platform-Dictated：平台主動呼叫外部系統 API
- 外部系統只需實作 get_task_list 與 get_task_detail 兩支端點
- external_context 為逃生艙欄位，平台不解析、僅透傳
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExternalTask:
    """
    外部系統回傳的任務摘要。
    對應 GET /getAntList（或等效端點）回應陣列中的單一項目。

    ant_id           : 外部系統的任務唯一識別碼
    ant_active       : 0=Pending, 1=Processing, 2=Completed
    ant_period       : 任務排程時間（ISO 8601 字串），可為 None
    external_context : 外部系統專屬欄位（如 lot_id, eqp_id），平台透傳不解析
    """
    ant_id: str
    ant_active: int = 0
    ant_period: str | None = None
    external_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExternalTaskDetail:
    """
    取得任務詳細資料的回應。
    通常包含非同步下載連結（ZIP、CSV 等），平台背景下載後處理。
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
    通用外部系統連接器抽象介面。
    平台主動呼叫外部系統 API；外部系統必須遵守平台定義的 API 契約。
    """

    @abstractmethod
    def get_ant_list(self) -> list[ExternalTask]:
        """回傳外部系統中所有待處理任務的摘要列表。"""
        ...

    @abstractmethod
    def get_ant_task_detail(self, task_id: str, format: str) -> ExternalTaskDetail:
        """
        回傳指定任務的詳細資料（通常是非同步下載連結）。

        task_id : 外部系統的任務識別碼
        format  : 平台要求的輸出格式（如 'coco', 'yolo-detection'）
        """
        ...

    def mark_task_claimed(self, task_id: str) -> None:
        """通知外部系統任務已被認領。如外部系統不支援此操作可不覆寫。"""
        pass

    @abstractmethod
    def health_check(self) -> ConnectorHealth:
        """檢查與外部系統的連線狀態。"""
        ...
