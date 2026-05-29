"""
annotation.integrations.connectors.fake_connector
--------------------------------------------------
測試用 Fake Connector。
實作 ExternalSystemConnector，回傳預設 fixture 資料，不發起任何網路請求。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from core.integrations.connector import (
    ConnectorHealth,
    ExternalSystemConnector,
    ExternalTask as AntTask,
    ExternalTaskDetail as TaskDetailResponse,
)


class FakeConnector(ExternalSystemConnector):
    """
    測試 / 開發用連接器，模擬外部系統的 REST API 行為。

    tasks        : 初始化時注入的任務清單，支援 antID/ant_id 兩種鍵名
    download_url : get_ant_task_detail 回傳的假 ZIP 連結
    """

    def __init__(
        self,
        tasks: list[dict[str, Any]] | None = None,
        download_url: str = "file:///fake/payload.zip",
    ) -> None:
        self._tasks: list[AntTask] = [
            AntTask(
                ant_id=t.get("ant_id", t.get("antID", f"task-{i}")),
                ant_active=t.get("ant_active", t.get("antActive", 0)),
                ant_period=t.get("ant_period", t.get("antPeriod")),
                external_context=t.get("external_context", {}),
            )
            for i, t in enumerate(tasks or [])
        ]
        self._download_url = download_url
        self._detail_calls: list[dict] = []

    # ── ExternalSystemConnector ───────────────────────────────────────────────

    def get_ant_list(self) -> list[AntTask]:
        return list(self._tasks)

    def get_ant_task_detail(self, ant_id: str, format: str) -> TaskDetailResponse:
        self._detail_calls.append({"ant_id": ant_id, "format": format})
        return TaskDetailResponse(download_url=self._download_url)

    def health_check(self) -> ConnectorHealth:
        return ConnectorHealth(connected=True, latency_ms=0)

    def deliver_result(
        self,
        ant_id: str,
        platform_task_id: str,
        annotation_json: dict,
        new_classification: str | None,
        annotated_by: str | None,
    ) -> dict:
        """No-op：不發 HTTP，直接回傳假成功回應。"""
        from datetime import timezone
        received_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {"status": "ok", "ant_id": ant_id, "received_at": received_at}

    # ── Test helpers ──────────────────────────────────────────────────────────

    def get_detail_calls(self) -> list[dict]:
        """回傳所有 get_ant_task_detail 的呼叫記錄，供 assertion 使用。"""
        return list(self._detail_calls)
