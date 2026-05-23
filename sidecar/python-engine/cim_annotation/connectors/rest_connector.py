from __future__ import annotations

"""
rest_connector.py — HTTP REST API pull/push connector.

Pulls image records from a paginated REST endpoint and pushes annotation
results via HTTP POST/PATCH.

connector.yaml example:
    connector:
      type: rest
      rest:
        base_url: "https://api.example.com"  # or env: CIM_CONNECTOR_BASE_URL
        token_env: CIM_CONNECTOR_TOKEN       # Bearer token
        pull_path: "/images"
        pull_page_param: "offset"
        pull_limit_param: "limit"
        pull_items_key: "data"               # JSON path to the items array
        push_path: "/annotations/{item_id}"
        push_method: "POST"                  # POST or PATCH
        version_path: "/annotations/versions"
"""

import json
import os
from pathlib import Path

from .base import PullConnector, PushConnector
from ..models import AnnotationPayload, FetchedItem, PushResult


def _resolve_base_url(base_url: str) -> str:
    if not base_url:
        base_url = os.environ.get("CIM_CONNECTOR_BASE_URL", "")
    if not base_url:
        raise ValueError(
            "RestConnector: no base_url configured (set base_url in yaml or CIM_CONNECTOR_BASE_URL env)"
        )
    return base_url.rstrip("/")


def _get_nested(obj: dict, dotpath: str):
    """Traverse dot-path like 'data.items' on a dict."""
    for key in dotpath.split("."):
        if not isinstance(obj, dict):
            return obj
        obj = obj.get(key, {})
    return obj


class RestConnector(PullConnector, PushConnector):
    """
    Pull images from a paginated REST API; push annotations via HTTP POST/PATCH.

    Uses the `requests` library (already a requirement).
    Session and auth headers are configured via connector.yaml + env vars.
    """

    def __init__(self, config: dict) -> None:
        import requests as _requests
        self._base_url = _resolve_base_url(config.get("base_url", ""))
        token = config.get("token") or os.environ.get(config.get("token_env", ""), "")
        self._session = _requests.Session()
        if token:
            self._session.headers["Authorization"] = f"Bearer {token}"
        self._session.headers["Content-Type"] = "application/json"
        self._session.headers["User-Agent"] = "CIM-AnnotationTool/1.0"

        self._pull_path: str = config.get("pull_path", "/images")
        self._pull_page_param: str = config.get("pull_page_param", "offset")
        self._pull_limit_param: str = config.get("pull_limit_param", "limit")
        self._pull_items_key: str = config.get("pull_items_key", "data")
        self._push_path_tpl: str = config.get("push_path", "/annotations/{item_id}")
        self._push_method: str = config.get("push_method", "POST").upper()
        self._version_path: str = config.get("version_path", "")
        self._timeout: int = int(config.get("timeout", 30))

        self._cache: list[FetchedItem] | None = None

    def _row_to_fetched_item(self, row: dict) -> FetchedItem:
        item_id = str(row.get("id", row.get("item_id", "")))
        file_path = str(row.get("file_path", "") or "")
        image_url = row.get("image_url") or row.get("url")
        width = row.get("width")
        height = row.get("height")
        file_hash = row.get("file_hash") or row.get("hash")
        meta = {k: v for k, v in row.items()
                if k not in ("id", "item_id", "file_path", "image_url", "url",
                             "width", "height", "file_hash", "hash")}
        return FetchedItem(
            item_id=item_id,
            file_path=file_path,
            image_url=str(image_url) if image_url else None,
            width=int(width) if width is not None else None,
            height=int(height) if height is not None else None,
            file_hash=str(file_hash) if file_hash else None,
            metadata=meta,
        )

    # ── PullConnector ─────────────────────────────────────────────────────────

    def fetch_page(self, offset: int, limit: int) -> list[FetchedItem]:
        url = f"{self._base_url}{self._pull_path}"
        params = {self._pull_page_param: offset, self._pull_limit_param: limit}
        try:
            resp = self._session.get(url, params=params, timeout=self._timeout)
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:
            raise RuntimeError(f"RestConnector.fetch_page failed: {exc}") from exc

        rows = _get_nested(body, self._pull_items_key)
        if not isinstance(rows, list):
            rows = body if isinstance(body, list) else []
        return [self._row_to_fetched_item(r) for r in rows]

    def resolve_image(self, item: FetchedItem, local_dir: Path) -> Path:
        if item.file_path and Path(item.file_path).exists():
            return Path(item.file_path)
        if item.image_url:
            suffix = Path(item.image_url.split("?")[0]).suffix or ".jpg"
            local = local_dir / f"{item.item_id}{suffix}"
            if not local.exists():
                try:
                    resp = self._session.get(item.image_url, timeout=self._timeout, stream=True)
                    resp.raise_for_status()
                    with open(local, "wb") as f:
                        for chunk in resp.iter_content(65536):
                            f.write(chunk)
                except Exception as exc:
                    raise RuntimeError(
                        f"RestConnector: could not download {item.image_url}: {exc}"
                    ) from exc
            return local
        raise FileNotFoundError(
            f"RestConnector: item {item.item_id} has no local file_path or image_url"
        )

    # ── PushConnector ─────────────────────────────────────────────────────────

    def push_batch(self, payloads: list[AnnotationPayload]) -> list[PushResult]:
        results: list[PushResult] = []
        for payload in payloads:
            try:
                body = {
                    "item_id": payload.item_id,
                    "remote_id": payload.remote_id,
                    "image_path": payload.image_path,
                    "image_width": payload.image_width,
                    "image_height": payload.image_height,
                    "shapes": payload.shapes,
                    "classification": payload.classification,
                    "confidence": payload.confidence,
                    "annotator": payload.annotator,
                    "annotated_at": payload.annotated_at,
                }
                path = self._push_path_tpl.format(item_id=payload.remote_id or payload.item_id)
                url = f"{self._base_url}{path}"
                method = getattr(self._session, self._push_method.lower())
                resp = method(url, json=body, timeout=self._timeout)
                resp.raise_for_status()
                results.append(PushResult(
                    item_id=payload.item_id,
                    success=True,
                    remote_ref=str(resp.json().get("id", payload.remote_id)),
                    error=None,
                ))
            except Exception as exc:
                results.append(PushResult(
                    item_id=payload.item_id,
                    success=False,
                    remote_ref=None,
                    error=str(exc),
                ))
        return results

    def check_remote_version(self, item_ids: list[str]) -> dict[str, str]:
        if not self._version_path or not item_ids:
            return {}
        url = f"{self._base_url}{self._version_path}"
        try:
            resp = self._session.post(
                url, json={"ids": item_ids}, timeout=self._timeout
            )
            resp.raise_for_status()
            data = resp.json()
            return {str(k): str(v) for k, v in data.items()}
        except Exception:
            return {}
