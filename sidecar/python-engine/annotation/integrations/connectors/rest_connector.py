"""
annotation.integrations.connectors.rest_connector
--------------------------------------------------
真實 HTTP Client，透過 httpx 呼叫外部系統 REST API。
實作 ExternalSystemConnector ABC，供 AnnotationService._get_connector 使用。

API 契約（外部系統必須遵守）：
  GET  {server_host_name}/getAntList
    Header: Authorization: Bearer {api_token}
    Response: JSON array of AntTask

  POST {server_host_name}/getAntTaskDetail
    Header: Authorization: Bearer {api_token}
    Body: {"antID": "...", "format": "coco"}
    Response: {"download_url": "..."}
"""
from __future__ import annotations

import time

import httpx

from core.integrations.connector import (
    ConnectorHealth,
    ExternalSystemConnector,
    ExternalTask as AntTask,
    ExternalTaskDetail as TaskDetailResponse,
)
from core.integrations.tenant import SystemTenant


class RestConnector(ExternalSystemConnector):
    """
    呼叫外部系統 REST API 的真實 HTTP Client。

    tenant  : 已向平台註冊的外部系統設定（server_host_name、api_token）
    timeout : httpx 請求逾時秒數（預設 30 秒）
    """

    def __init__(self, tenant: SystemTenant, timeout: float = 30.0) -> None:
        self._tenant = tenant
        self._timeout = timeout
        self._headers = (
            {"Authorization": f"Bearer {tenant.api_token}"}
            if tenant.api_token
            else {}
        )
        self._base = tenant.server_host_name  # 已去除末尾斜線（profiles.load_profile 保證）

    # ── ExternalSystemConnector ───────────────────────────────────────────────

    def get_ant_list(self) -> list[AntTask]:
        """
        GET {base}/getAntList
        成功 (200) → 回傳 AntTask 列表
        401        → raise PermissionError
        其他非 200 → raise RuntimeError（含 status code）
        """
        url = f"{self._base}/getAntList"
        resp = httpx.get(url, headers=self._headers, timeout=self._timeout)

        if resp.status_code == 401:
            raise PermissionError(
                f"外部系統拒絕授權（401）：{url}。請確認 api_token 是否正確。"
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"GET {url} 回傳非預期狀態碼 {resp.status_code}：{resp.text[:200]}"
            )

        raw_list: list[dict] = resp.json()
        return [
            AntTask(
                ant_id=item.get("antID", item.get("ant_id", "")),
                ant_active=int(item.get("antActive", item.get("ant_active", 0))),
                ant_period=item.get("antPeriod", item.get("ant_period")),
                external_context={
                    k: v
                    for k, v in item.items()
                    if k not in {"antID", "ant_id", "antActive", "ant_active", "antPeriod", "ant_period"}
                },
            )
            for item in raw_list
        ]

    def get_ant_task_detail(self, ant_id: str, format: str) -> TaskDetailResponse:
        """
        POST {base}/getAntTaskDetail
        Body: {"antID": ant_id, "format": format}
        成功 (200) → 回傳 TaskDetailResponse
        401        → raise PermissionError
        其他非 200 → raise RuntimeError（含 status code）
        """
        url = f"{self._base}/getAntTaskDetail"
        payload = {"antID": ant_id, "format": format}
        resp = httpx.post(url, json=payload, headers=self._headers, timeout=self._timeout)

        if resp.status_code == 401:
            raise PermissionError(
                f"外部系統拒絕授權（401）：{url}。請確認 api_token 是否正確。"
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"POST {url} 回傳非預期狀態碼 {resp.status_code}：{resp.text[:200]}"
            )

        data: dict = resp.json()
        return TaskDetailResponse(download_url=data["download_url"])

    def mark_task_claimed(self, ant_id: str) -> None:
        """
        PATCH {base}/tasks/{ant_id}/claim
        成功 (200) → 靜默 return
        409        → raise RuntimeError（任務已被他人認領）
        連線失敗   → raise ConnectionRefusedError
        """
        url = f"{self._base}/tasks/{ant_id}/claim"
        try:
            resp = httpx.patch(url, headers=self._headers, timeout=self._timeout)
        except httpx.ConnectError as exc:
            raise ConnectionRefusedError(f"無法連線至外部系統：{url}") from exc

        if resp.status_code == 409:
            raise RuntimeError("任務已被他人認領")
        if resp.status_code == 404:
            raise RuntimeError(f"外部系統找不到任務 {ant_id!r}（404）")
        if resp.status_code != 200:
            raise RuntimeError(
                f"PATCH {url} 回傳非預期狀態碼 {resp.status_code}：{resp.text[:200]}"
            )

    def health_check(self) -> ConnectorHealth:
        """
        GET {base}/getAntList，只測連線狀態，不解析回應內容。
        成功     → ConnectorHealth(connected=True, latency_ms=...)
        任何例外 → ConnectorHealth(connected=False, error=str(exc))
        """
        url = f"{self._base}/getAntList"
        start_ms = time.monotonic()
        try:
            resp = httpx.get(url, headers=self._headers, timeout=self._timeout)
            elapsed_ms = int((time.monotonic() - start_ms) * 1000)
            # 只要能拿到 HTTP 回應（無論 status）即視為連線成功
            return ConnectorHealth(connected=True, latency_ms=elapsed_ms)
        except Exception as exc:
            return ConnectorHealth(connected=False, error=str(exc))
