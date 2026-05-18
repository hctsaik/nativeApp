from __future__ import annotations

import json
import urllib.request
from typing import Any

import httpx

from .config import SIDECAR_BASE


class SidecarError(Exception):
    """Raised when the sidecar API returns an error."""


def _live_sidecar_base() -> str:
    """Query the dev-log server for the current sidecar port; fall back to config."""
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:19222/dev/status", timeout=2
        ) as resp:
            data = json.loads(resp.read())
            port = int(data.get("sidecarControlPort", 0))
            if port:
                return f"http://127.0.0.1:{port}"
    except Exception:
        pass
    return SIDECAR_BASE


class SidecarClient:
    """Async HTTP client for the CIM Python sidecar API."""

    def __init__(self, base_url: str | None = None, timeout: float = 10.0) -> None:
        self._explicit_base = base_url is not None
        self._base = (base_url or _live_sidecar_base()).rstrip("/")
        self._timeout = timeout

    def _refresh_base(self) -> None:
        if not self._explicit_base:
            self._base = _live_sidecar_base().rstrip("/")

    async def health(self) -> str:
        """GET /health — returns 'ok' or raises SidecarError."""
        self._refresh_base()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                r = await client.get(f"{self._base}/health")
                r.raise_for_status()
                return r.json().get("status", "ok")
            except httpx.HTTPError as exc:
                raise SidecarError(f"health check failed: {exc}") from exc

    async def list_tools(self) -> list[dict[str, Any]]:
        """GET /tools — returns list of tool info dicts."""
        self._refresh_base()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                r = await client.get(f"{self._base}/tools")
                r.raise_for_status()
                return r.json()
            except httpx.HTTPError as exc:
                raise SidecarError(f"list_tools failed: {exc}") from exc

    async def start_tool(self, tool_id: str) -> dict[str, Any]:
        """POST /tools/{tool_id}/start — returns {input_url, output_url, ...}."""
        self._refresh_base()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                r = await client.post(f"{self._base}/tools/{tool_id}/start")
                r.raise_for_status()
                return r.json()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text
                raise SidecarError(f"start_tool({tool_id!r}) failed [{exc.response.status_code}]: {detail}") from exc
            except httpx.HTTPError as exc:
                raise SidecarError(f"start_tool({tool_id!r}) failed: {exc}") from exc

    async def stop_tool(self) -> str:
        """POST /tools/stop — returns 'stopped'."""
        self._refresh_base()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                r = await client.post(f"{self._base}/tools/stop")
                r.raise_for_status()
                return r.json().get("status", "stopped")
            except httpx.HTTPError as exc:
                raise SidecarError(f"stop_tool failed: {exc}") from exc
