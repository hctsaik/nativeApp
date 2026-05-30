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
    "list_root": "",   # dot-path to the array inside an envelope (e.g. "data.items"); "" = response is the array
    "detail_root": "", # dot-path to the object inside a detail envelope (e.g. "data"); "" = response is the object
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
        for k in ("list_path", "detail_path", "claim_path", "detail_method", "list_root", "detail_root"):
            if mapping.get(k):
                m[k] = mapping[k]
        if isinstance(mapping.get("fields"), dict):
            m["fields"] = {**_DEFAULTS["fields"], **mapping["fields"]}
    return m


def dig(data, dot_path: str):
    """Walk a dot-path (e.g. 'data.items') into nested dicts (pure). '' → data."""
    if not dot_path:
        return data
    cur = data
    for part in dot_path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def extract_list(data, list_root: str) -> list:
    """Extract the task array from a response, honouring an envelope path (pure).

    Falls back gracefully: if list_root misses, but the response itself is a list
    use it; otherwise return []."""
    if list_root:
        found = dig(data, list_root)
        if isinstance(found, list):
            return found
    if isinstance(data, list):
        return data
    return []


# Common non-numeric status strings → our 0=pending / 1=processing / 2=completed.
_STATUS_WORDS = {
    "pending": 0, "open": 0, "new": 0, "queued": 0, "todo": 0, "待認領": 0, "待處理": 0,
    "processing": 1, "in_progress": 1, "claimed": 1, "running": 1, "標記中": 1, "處理中": 1,
    "completed": 2, "done": 2, "finished": 2, "closed": 2, "已標記": 2, "已完成": 2,
}


def coerce_active(value) -> int:
    """Coerce an external status into our 0/1/2 code, tolerating arbitrary REST
    variants: ints pass through, numeric strings parse, known status words map,
    anything else → 0 (never raises — a weird status must not break the list)."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if value is None:
        return 0
    s = str(value).strip()
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return _STATUS_WORDS.get(s.lower(), 0)


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
        ant_active=coerce_active(_pick("ant_active", 0)),
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
        items = extract_list(resp.json(), self._m.get("list_root", ""))
        return [map_list_item(it, self._m["fields"]) for it in items if isinstance(it, dict)]

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
        # Honour a detail envelope (e.g. {"data": {"download_url": ...}}) the same
        # way list_root does for the list endpoint.
        root = dig(resp.json(), self._m.get("detail_root", ""))
        data: dict = root if isinstance(root, dict) else resp.json()
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
