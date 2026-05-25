"""
annotation.integrations.contracts
----------------------------------
定義外部系統連接器的共用資料結構（dataclass）與抽象介面（ABC）。
所有 connector 實作必須繼承 ExternalSystemConnector 並實作全部抽象方法。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PaginationToken:
    """分頁游標。value=None 代表第一頁；回傳 None 代表已無更多頁。"""
    value: str | None = None  # None = first page


@dataclass
class ExternalTask:
    """外部系統的一個標注任務單元。"""
    external_id: str
    image_uri: str
    metadata: dict[str, Any] = field(default_factory=dict)
    rework_reason: str | None = None  # 若為重工任務，記錄原因


@dataclass
class ResolvedAsset:
    """
    解析後的媒體資源位址。
    asset_type: "local_path" | "remote_url"
    ttl_seconds: 若為簽署 URL，到期秒數（None = 永不過期）
    """
    asset_type: str
    value: str
    ttl_seconds: int | None = None


@dataclass
class RawLabelSchema:
    """從外部系統取回的原始 label schema，尚未轉換為 CIM 內部格式。"""
    raw: dict[str, Any]
    source_format: str  # e.g. "fake" | "yolo_txt" | "oracle_json"


@dataclass
class ExportPayload:
    """準備推送回外部系統的標注資料包。"""
    format_id: str        # 目標格式識別碼
    data: Any             # 序列化後的標注資料
    conversion_report: dict  # 轉換過程的統計 / 警告


@dataclass
class PushResult:
    """推送標注結果至外部系統後的回報。"""
    success: bool
    rows_written: int = 0
    external_ref: str | None = None  # 外部系統回傳的參考 ID（如有）
    error: str | None = None         # 失敗時的錯誤描述


@dataclass
class ConnectorHealth:
    """連接器健康檢查結果。"""
    connected: bool
    latency_ms: int | None = None
    version: str | None = None       # 外部系統回報的版本（如有）
    error: str | None = None


class ExternalSystemConnector(ABC):
    """
    所有外部系統連接器必須實作的抽象介面。
    每個 connector 對應一種外部系統（Oracle、REST API、File system 等）。
    """

    @abstractmethod
    def list_tasks(
        self,
        query: dict,
        pagination_token: PaginationToken,
    ) -> tuple[list[ExternalTask], PaginationToken]:
        """
        列出外部系統中待標注的任務。
        回傳 (tasks, next_token)；next_token.value=None 代表最後一頁。
        """
        ...

    @abstractmethod
    def resolve_asset(self, task: ExternalTask) -> ResolvedAsset:
        """
        將 task.image_uri 解析為可直接存取的媒體位址。
        例如：將 object-storage key 轉換為簽署 URL，或驗證本地路徑是否存在。
        """
        ...

    @abstractmethod
    def load_label_schema(self) -> RawLabelSchema:
        """從外部系統取回原始 label schema 定義。"""
        ...

    @abstractmethod
    def push_annotations(
        self,
        task_id: str,
        payload: ExportPayload,
        mode: str,
    ) -> PushResult:
        """
        將標注結果推送回外部系統。
        mode: "upsert" | "append" | "replace"（由 profile 決定）
        """
        ...

    @abstractmethod
    def health_check(self) -> ConnectorHealth:
        """檢查與外部系統的連線狀態。"""
        ...
