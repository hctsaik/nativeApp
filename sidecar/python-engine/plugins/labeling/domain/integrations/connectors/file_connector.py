"""
annotation.integrations.connectors.file_connector
--------------------------------------------------
FileConnector — 以本地檔案系統模擬外部系統的連接器。
適用於離線開發與整合測試，行為對應真實 REST connector 但不發網路請求。

SystemTenant extra 欄位（設定於 api_token 之外，以 JSON extra key 傳入）：
    ant_list_path : str — get_ant_list 讀取的任務清單 JSON 檔（ant list JSON array）
    zip_root      : str — get_ant_task_detail 回傳的 ZIP 所在目錄；
                          回傳 file://{zip_root}/{ant_id}.zip 形式的 URL
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from core.integrations.connector import (
    ConnectorHealth,
    ExternalSystemConnector,
    ExternalTask as AntTask,
    ExternalTaskDetail as TaskDetailResponse,
)
from core.integrations.tenant import SystemTenant


class FileConnector(ExternalSystemConnector):
    """
    本地檔案系統 connector，模擬外部系統 REST API。

    get_ant_list()        ← 讀取 ant_list_path JSON 檔
    get_ant_task_detail() ← 回傳 file:// URL 指向 zip_root/{ant_id}.zip
    health_check()        ← 檢查 ant_list_path 或 zip_root 是否存在
    """

    def __init__(self, tenant: SystemTenant, **extra: str) -> None:
        self._tenant = tenant
        self._ant_list_path: Path | None = (
            Path(extra["ant_list_path"]) if "ant_list_path" in extra else None
        )
        self._zip_root: Path | None = (
            Path(extra["zip_root"]) if "zip_root" in extra else None
        )

    # ── ExternalSystemConnector ───────────────────────────────────────────────

    def get_ant_list(self) -> list[AntTask]:
        """讀取 ant_list_path JSON 檔，回傳 AntTask 列表。"""
        if self._ant_list_path is None:
            raise ValueError("FileConnector.get_ant_list 需要 ant_list_path 參數")
        if not self._ant_list_path.exists():
            raise FileNotFoundError(f"ant_list_path 不存在：{self._ant_list_path}")

        raw: list[dict] = json.loads(self._ant_list_path.read_text(encoding="utf-8"))
        return [
            AntTask(
                ant_id=item.get("antID", item.get("ant_id", f"task-{i}")),
                ant_active=item.get("antActive", item.get("ant_active", 0)),
                ant_period=item.get("antPeriod", item.get("ant_period")),
                external_context=item.get("external_context", {}),
            )
            for i, item in enumerate(raw)
        ]

    def get_ant_task_detail(self, ant_id: str, format: str) -> TaskDetailResponse:
        """回傳 file:// URL 指向本地 ZIP 檔，供平台背景下載。"""
        if self._zip_root is None:
            raise ValueError("FileConnector.get_ant_task_detail 需要 zip_root 參數")
        safe_id = ant_id.replace("/", "_").replace("\\", "_")
        zip_path = self._zip_root / f"{safe_id}.zip"
        return TaskDetailResponse(download_url=zip_path.as_uri())

    def health_check(self) -> ConnectorHealth:
        start = time.monotonic()
        check = self._ant_list_path or self._zip_root
        if check is None:
            return ConnectorHealth(
                connected=False,
                error="FileConnector: 未設定 ant_list_path 或 zip_root",
            )
        latency_ms = int((time.monotonic() - start) * 1000)
        if check.exists():
            return ConnectorHealth(connected=True, latency_ms=latency_ms)
        return ConnectorHealth(
            connected=False,
            latency_ms=latency_ms,
            error=f"路徑不存在：{check}",
        )

    def deliver_result(
        self,
        ant_id: str,
        platform_task_id: str,
        annotation_json: dict,
        new_classification: str | None,
        annotated_by: str | None,
    ) -> dict:
        """FileConnector is local-only; delivery is a no-op."""
        from datetime import datetime, timezone
        return {
            "status": "ok",
            "ant_id": ant_id,
            "received_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
