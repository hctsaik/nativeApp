"""Declarative REST connector —接「REST 變體」外部系統免寫 class。

Most new external task systems are "just another REST API" with different
endpoint paths and field names. Instead of writing a new connector class, an
integrator declares the differences in `external_systems.yaml`:

    - system_name: AcmeTasks
      server_host_name: https://acme.example/api
      target_format: coco
      api_token_env: ACME_TOKEN
      connector_type: rest            # (or omit; rest is the http(s) default)
      rest_mapping:
        list_path:   /v2/tasks
        detail_path: /v2/tasks/detail
        claim_path:  /v2/tasks/{ant_id}/claim
        detail_method: POST           # GET | POST
        fields:                       # response key → our field
          ant_id:       id
          ant_active:   status
          ant_period:   due_at
          download_url: artifact_url

Anything omitted falls back to the built-in iWISC contract, so an empty mapping
behaves exactly like the original RestConnector. The path-building and field-
mapping are pure functions (`resolve_paths`, `map_list_item`) for unit testing.
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

# Built-in iWISC contract — the defaults a mapping overrides.
_DEFAULTS = {
    "list_path": "/getAntList",
    "detail_path": "/getAntTaskDetail",
    "claim_path": "/tasks/{ant_id}/claim",
    "detail_method": "POST",
    "fields": {
        "ant_id": "antID",
        "ant_active": "antActive",
        "ant_period": "antPeriod",
        "download_url": "download_url",
    },
}


def resolve_paths(mapping: dict | None) -> dict:
    """Merge a (partial) declarative mapping over the built-in defaults (pure)."""
    m = dict(_DEFAULTS)
    if mapping:
        for k in ("list_path", "detail_path", "claim_path", "detail_method"):
            if mapping.get(k):
                m[k] = mapping[k]
        if isinstance(mapping.get("fields"), dict):
            m["fields"] = {**_DEFAULTS["fields"], **mapping["fields"]}
    return m


def map_list_item(item: dict, fields: dict) -> AntTask:
    """Map one raw response dict to an AntTask using the field mapping (pure).

    Accepts both the mapped key and our canonical key (so default-shaped
    payloads keep working). Unmapped keys go to external_context.
    """
    def _pick(canonical: str, default=None):
        src = fields.get(canonical, canonical)
        return item.get(src, item.get(canonical, default))

    consumed = set()
    for canonical in ("ant_id", "ant_active", "ant_period"):
        consumed.add(fields.get(canonical, canonical))
        consumed.add(canonical)
    return AntTask(
        ant_id=str(_pick("ant_id", "")),
        ant_active=int(_pick("ant_active", 0) or 0),
        ant_period=_pick("ant_period"),
        external_context={k: v for k, v in item.items() if k not in consumed},
    )


class ConfigurableRestConnector(ExternalSystemConnector):
    """REST connector whose endpoints/fields come from a declarative mapping."""

    def __init__(self, tenant: SystemTenant, mapping: dict | None = None,
                 timeout: float = 30.0) -> None:
        self._tenant = tenant
        self._timeout = timeout
        self._headers = (
            {"Authorization": f"Bearer {tenant.api_token}"} if tenant.api_token else {}
        )
        self._base = tenant.server_host_name.rstrip("/")
        self._m = resolve_paths(mapping if mapping is not None
                                else getattr(tenant, "connector_config", None))

    def _url(self, path: str) -> str:
        return f"{self._base}/{path.lstrip('/')}"

    def get_ant_list(self) -> list[AntTask]:
        url = self._url(self._m["list_path"])
        resp = httpx.get(url, headers=self._headers, timeout=self._timeout)
        if resp.status_code == 401:
            raise PermissionError(f"外部系統拒絕授權（401）：{url}。請確認 api_token 是否正確。")
        if resp.status_code != 200:
            raise RuntimeError(f"GET {url} 回傳非預期狀態碼 {resp.status_code}：{resp.text[:200]}")
        return [map_list_item(it, self._m["fields"]) for it in resp.json()]

    def get_ant_task_detail(self, ant_id: str, format: str) -> TaskDetailResponse:
        url = self._url(self._m["detail_path"])
        payload = {"antID": ant_id, "format": format}
        if (self._m["detail_method"] or "POST").upper() == "GET":
            resp = httpx.get(url, params=payload, headers=self._headers, timeout=self._timeout)
        else:
            resp = httpx.post(url, json=payload, headers=self._headers, timeout=self._timeout)
        if resp.status_code == 401:
            raise PermissionError(f"外部系統拒絕授權（401）：{url}。請確認 api_token 是否正確。")
        if resp.status_code != 200:
            raise RuntimeError(f"{url} 回傳非預期狀態碼 {resp.status_code}：{resp.text[:200]}")
        data: dict = resp.json()
        dl_key = self._m["fields"].get("download_url", "download_url")
        return TaskDetailResponse(download_url=data.get(dl_key, data.get("download_url", "")))

    def mark_task_claimed(self, ant_id: str) -> None:
        url = self._url(self._m["claim_path"].replace("{ant_id}", str(ant_id)))
        try:
            resp = httpx.patch(url, headers=self._headers, timeout=self._timeout)
        except httpx.ConnectError as exc:
            raise ConnectionRefusedError(f"無法連線至外部系統：{url}") from exc
        if resp.status_code == 409:
            raise RuntimeError("任務已被他人認領")
        if resp.status_code == 404:
            raise RuntimeError(f"外部系統找不到任務 {ant_id!r}（404）")
        if resp.status_code != 200:
            raise RuntimeError(f"PATCH {url} 回傳非預期狀態碼 {resp.status_code}：{resp.text[:200]}")

    def health_check(self) -> ConnectorHealth:
        url = self._url(self._m["list_path"])
        start_ms = time.monotonic()
        try:
            httpx.get(url, headers=self._headers, timeout=self._timeout)
            return ConnectorHealth(connected=True, latency_ms=int((time.monotonic() - start_ms) * 1000))
        except Exception as exc:  # noqa: BLE001
            return ConnectorHealth(connected=False, error=str(exc))
