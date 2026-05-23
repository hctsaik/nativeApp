from __future__ import annotations

"""
sql_connector.py — SQLAlchemy-based pull/push connector.

Pulls image records from a SQL table and pushes annotation JSON back as a
column update.  Requires SQLAlchemy (optional dependency).

connector.yaml example:
    connector:
      type: sql
      sql:
        dsn: "postgresql+psycopg2://user:pw@host/db"   # or env: CIM_CONNECTOR_DSN
        pull_query: "SELECT id, file_path, image_url, width, height FROM images WHERE active=1"
        push_table: "annotations"
        push_id_column: "image_id"
        push_json_column: "xanylabeling_json"
        push_updated_at_column: "updated_at"
        version_query: "SELECT id, updated_at FROM annotations WHERE id IN :ids"
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import PullConnector, PushConnector
from ..models import AnnotationPayload, FetchedItem, PushResult


def _require_sqlalchemy():
    try:
        import sqlalchemy
        return sqlalchemy
    except ImportError:
        raise ImportError(
            "SQLAlchemy is required for SqlConnector. "
            "Install with: pip install sqlalchemy"
        )


def _resolve_dsn(dsn: str) -> str:
    if not dsn:
        dsn = os.environ.get("CIM_CONNECTOR_DSN", "")
    if not dsn:
        raise ValueError("SqlConnector: no DSN configured (set dsn in yaml or CIM_CONNECTOR_DSN env)")
    return dsn


class SqlConnector(PullConnector, PushConnector):
    """
    Pull images from a SQL SELECT query; push annotations back as a JSON column.

    The pull query must return at minimum: id, file_path (or image_url).
    Optional columns: width, height, file_hash, and any extra metadata columns.

    The push step performs an UPSERT into push_table with:
      - push_id_column = item_id (remote PK)
      - push_json_column = serialised X-AnyLabeling JSON
      - push_updated_at_column = now() in UTC ISO format
    """

    def __init__(self, config: dict) -> None:
        sa = _require_sqlalchemy()
        dsn = _resolve_dsn(config.get("dsn", ""))
        self._engine = sa.create_engine(dsn, future=True)
        self._pull_query: str = config.get(
            "pull_query",
            "SELECT id, file_path FROM images",
        )
        self._push_table: str = config.get("push_table", "annotations")
        self._push_id_col: str = config.get("push_id_column", "image_id")
        self._push_json_col: str = config.get("push_json_column", "xanylabeling_json")
        self._push_updated_at_col: str = config.get("push_updated_at_column", "updated_at")
        self._version_query: str = config.get("version_query", "")
        self._rows: list[dict] | None = None  # lazy cache

    def _fetch_all_rows(self) -> list[dict]:
        if self._rows is not None:
            return self._rows
        sa = _require_sqlalchemy()
        with self._engine.connect() as conn:
            result = conn.execute(sa.text(self._pull_query))
            keys = list(result.keys())
            self._rows = [dict(zip(keys, row)) for row in result]
        return self._rows

    def _row_to_fetched_item(self, row: dict) -> FetchedItem:
        item_id = str(row.get("id", ""))
        file_path = str(row.get("file_path", "") or "")
        image_url = row.get("image_url") or row.get("url")
        width = row.get("width")
        height = row.get("height")
        file_hash = row.get("file_hash") or row.get("hash")
        meta = {k: v for k, v in row.items()
                if k not in ("id", "file_path", "image_url", "url",
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
        rows = self._fetch_all_rows()
        page = rows[offset: offset + limit]
        return [self._row_to_fetched_item(r) for r in page]

    def resolve_image(self, item: FetchedItem, local_dir: Path) -> Path:
        if item.file_path and Path(item.file_path).exists():
            return Path(item.file_path)
        if item.image_url:
            local = local_dir / f"{item.item_id}{Path(item.image_url).suffix or '.jpg'}"
            if not local.exists():
                try:
                    import urllib.request
                    urllib.request.urlretrieve(item.image_url, str(local))
                except Exception as exc:
                    raise RuntimeError(
                        f"SqlConnector: could not download {item.image_url}: {exc}"
                    ) from exc
            return local
        raise FileNotFoundError(
            f"SqlConnector: item {item.item_id} has no local file_path or image_url"
        )

    # ── PushConnector ─────────────────────────────────────────────────────────

    def push_batch(self, payloads: list[AnnotationPayload]) -> list[PushResult]:
        sa = _require_sqlalchemy()
        results: list[PushResult] = []
        now = datetime.now(timezone.utc).isoformat()

        for payload in payloads:
            try:
                ann_json = json.dumps({
                    "imagePath": Path(payload.image_path).name,
                    "imageWidth": payload.image_width,
                    "imageHeight": payload.image_height,
                    "shapes": payload.shapes,
                    "flags": {
                        "classification": payload.classification or "",
                    },
                    "annotator": payload.annotator,
                    "annotated_at": payload.annotated_at,
                    "confidence": payload.confidence,
                }, ensure_ascii=False)

                with self._engine.begin() as conn:
                    conn.execute(
                        sa.text(
                            f"INSERT INTO {self._push_table} "
                            f"({self._push_id_col}, {self._push_json_col}, "
                            f"{self._push_updated_at_col}) "
                            f"VALUES (:iid, :json, :updated_at) "
                            f"ON CONFLICT ({self._push_id_col}) DO UPDATE SET "
                            f"{self._push_json_col}=excluded.{self._push_json_col}, "
                            f"{self._push_updated_at_col}=excluded.{self._push_updated_at_col}"
                        ),
                        {"iid": payload.remote_id or payload.item_id,
                         "json": ann_json,
                         "updated_at": now},
                    )

                results.append(PushResult(
                    item_id=payload.item_id,
                    success=True,
                    remote_ref=payload.remote_id,
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
        if not self._version_query or not item_ids:
            return {}
        sa = _require_sqlalchemy()
        try:
            with self._engine.connect() as conn:
                result = conn.execute(
                    sa.text(self._version_query.replace(":ids", f"({','.join(repr(i) for i in item_ids)})")),
                )
                rows = result.fetchall()
                return {str(r[0]): str(r[1]) for r in rows}
        except Exception:
            return {}
