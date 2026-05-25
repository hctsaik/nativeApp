"""
annotation.integrations.connectors.fake_connector
---------------------------------------------------
FakeConnector — 僅用於單元測試的假連接器。
使用 fixture 資料回應所有呼叫，並記錄 push_annotations 的呼叫歷程供 assertion。
不依賴任何外部服務或檔案系統。
"""
from __future__ import annotations

from typing import Any

from annotation.integrations.contracts import (
    ConnectorHealth,
    ExportPayload,
    ExternalSystemConnector,
    ExternalTask,
    PaginationToken,
    PushResult,
    RawLabelSchema,
    ResolvedAsset,
)


class FakeConnector(ExternalSystemConnector):
    """
    測試用假連接器。
    所有方法使用建構子傳入的 fixture 資料回應，不做任何 I/O。
    """

    def __init__(self, tasks: list[dict], schema: dict) -> None:
        """
        初始化假連接器。

        tasks : 每個元素為 dict，至少包含 "external_id" 與 "image_uri" 欄位。
        schema: 模擬的 label schema 原始 dict。
        """
        self._tasks: list[ExternalTask] = [
            ExternalTask(
                external_id=t["external_id"],
                image_uri=t["image_uri"],
                metadata=t.get("metadata", {}),
                rework_reason=t.get("rework_reason"),
            )
            for t in tasks
        ]
        self._schema: dict[str, Any] = schema
        self._push_calls: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # ExternalSystemConnector interface
    # ------------------------------------------------------------------

    def list_tasks(
        self,
        query: dict,
        pagination_token: PaginationToken,
    ) -> tuple[list[ExternalTask], PaginationToken]:
        """回傳所有 fixture tasks（忽略 query 與 pagination_token）。"""
        return list(self._tasks), PaginationToken(value=None)

    def resolve_asset(self, task: ExternalTask) -> ResolvedAsset:
        """直接回傳 task.image_uri 作為 local_path，不做任何驗證。"""
        return ResolvedAsset(asset_type="local_path", value=task.image_uri)

    def load_label_schema(self) -> RawLabelSchema:
        """回傳建構子傳入的 schema fixture。"""
        return RawLabelSchema(raw=self._schema, source_format="fake")

    def push_annotations(
        self,
        task_id: str,
        payload: ExportPayload,
        mode: str,
    ) -> PushResult:
        """記錄呼叫參數並回傳成功結果。"""
        self._push_calls.append(
            {
                "task_id": task_id,
                "format_id": payload.format_id,
                "mode": mode,
                "data": payload.data,
            }
        )
        return PushResult(success=True, rows_written=1)

    def health_check(self) -> ConnectorHealth:
        """永遠回傳 connected=True，latency_ms=0。"""
        return ConnectorHealth(connected=True, latency_ms=0)

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    def get_push_calls(self) -> list[dict[str, Any]]:
        """回傳所有 push_annotations 呼叫的記錄，供 test assertion 使用。"""
        return list(self._push_calls)
