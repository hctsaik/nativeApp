from __future__ import annotations

"""
_data_connector.py — DataConnector 抽象介面

每個子系統實作自己的 connector，module_019 透過選擇器呼叫對應的 connector。
connector 負責：
  1. 列出可用資料集
  2. 列出資料集的 item 清單（含下載 URL）
  3. 下載圖片到本機 cache 並回報進度
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class DatasetInfo:
    dataset_id: str
    name: str
    item_count: int
    description: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class RemoteItem:
    item_id: str
    file_name: str           # e.g. "001.jpg"
    download_url: str        # presigned URL or direct URL
    width: int = 0
    height: int = 0
    has_annotation: bool = False   # Service 告知此 item 是否附帶標注
    annotation_url: str = ""       # presigned URL for annotation JSON（可選）
    metadata: dict = field(default_factory=dict)


# Progress callback: (downloaded, total, current_filename) -> None
ProgressCallback = Callable[[int, int, str], None]


class DataConnector(ABC):
    """所有遠端資料來源的共用介面。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """顯示在 UI 選擇器的名稱，例如 '系統 A'。"""

    @abstractmethod
    def list_datasets(self) -> list[DatasetInfo]:
        """列出此 connector 可存取的資料集。"""

    @abstractmethod
    def list_items(self, dataset_id: str) -> list[RemoteItem]:
        """列出資料集的所有 item（含 download_url）。"""

    def on_download_complete(self, dataset_id: str, local_dir: str) -> None:
        """下載完成後的 hook，可用於回寫子系統（可選覆寫）。"""


class ZipPackageConnector(DataConnector):
    """
    打一發 Service，回傳 zip 壓縮包的 connector。
    zip 內容：images/ + annotations/ + manifest.json
    """

    def __init__(self, service_base_url: str, timeout: int = 30):
        self._base_url = service_base_url.rstrip("/")
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "ZIP Package Service"

    def list_datasets(self) -> list[DatasetInfo]:
        import requests
        resp = requests.get(f"{self._base_url}/datasets", timeout=self._timeout)
        resp.raise_for_status()
        return [
            DatasetInfo(
                dataset_id=d["dataset_id"],
                name=d["name"],
                item_count=d.get("item_count", 0),
                description=d.get("description", ""),
                metadata=d.get("metadata", {}),
            )
            for d in resp.json()
        ]

    def list_items(self, dataset_id: str) -> list[RemoteItem]:
        """
        對 ZipPackageConnector 而言，list_items 不直接呼叫，
        改由 download_zip() 整包下載後從 manifest.json 讀取。
        此方法回傳空清單，實際 item 由 019_process.py 解壓後取得。
        """
        return []

    def get_zip_url(self, dataset_id: str) -> str:
        """回傳 zip 下載 URL。"""
        return f"{self._base_url}/datasets/{dataset_id}/download"
