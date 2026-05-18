from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from annotation.core.models import (
    AnnotationSet,
    Dataset,
    ImageAsset,
    LabelSchema,
    ReviewDecision,
)


class SQLiteMetadataStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS datasets (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_assets_dataset_checksum
                    ON assets(dataset_id, checksum);
                CREATE TABLE IF NOT EXISTS schemas (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS annotation_sets (
                    id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL,
                    schema_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS review_decisions (
                    id TEXT PRIMARY KEY,
                    target_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS exports (
                    id TEXT PRIMARY KEY,
                    annotation_set_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                """
            )

    def save_dataset(self, dataset: Dataset) -> Dataset:
        self._upsert("datasets", dataset.id, dataset.to_dict())
        return dataset

    def get_dataset(self, dataset_id: str) -> Dataset | None:
        row = self._get("datasets", dataset_id)
        return Dataset.from_dict(row) if row else None

    def list_datasets(self) -> list[Dataset]:
        with self.connect() as conn:
            rows = conn.execute("SELECT payload FROM datasets ORDER BY id").fetchall()
        return [Dataset.from_dict(json.loads(row["payload"])) for row in rows]

    def save_asset(self, asset: ImageAsset) -> ImageAsset:
        payload = json.dumps(asset.to_dict(), ensure_ascii=False)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO assets (id, dataset_id, checksum, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  dataset_id=excluded.dataset_id,
                  checksum=excluded.checksum,
                  payload=excluded.payload
                """,
                (asset.id, asset.dataset_id, asset.checksum, payload),
            )
        return asset

    def find_asset_by_checksum(self, dataset_id: str, checksum: str) -> ImageAsset | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload FROM assets WHERE dataset_id = ? AND checksum = ?",
                (dataset_id, checksum),
            ).fetchone()
        return ImageAsset.from_dict(json.loads(row["payload"])) if row else None

    def list_assets(self, dataset_id: str) -> list[ImageAsset]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM assets WHERE dataset_id = ? ORDER BY id",
                (dataset_id,),
            ).fetchall()
        return [ImageAsset.from_dict(json.loads(row["payload"])) for row in rows]

    def save_schema(self, schema: LabelSchema) -> LabelSchema:
        self._upsert("schemas", schema.id, schema.to_dict())
        return schema

    def get_schema(self, schema_id: str) -> LabelSchema | None:
        row = self._get("schemas", schema_id)
        return LabelSchema.from_dict(row) if row else None

    def save_annotation_set(self, annotation_set: AnnotationSet) -> AnnotationSet:
        payload = json.dumps(annotation_set.to_dict(), ensure_ascii=False)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO annotation_sets (id, dataset_id, schema_id, state, version, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  dataset_id=excluded.dataset_id,
                  schema_id=excluded.schema_id,
                  state=excluded.state,
                  version=excluded.version,
                  payload=excluded.payload
                """,
                (
                    annotation_set.id,
                    annotation_set.dataset_id,
                    annotation_set.schema_id,
                    annotation_set.state,
                    annotation_set.version,
                    payload,
                ),
            )
        return annotation_set

    def get_annotation_set(self, annotation_set_id: str) -> AnnotationSet | None:
        row = self._get("annotation_sets", annotation_set_id)
        return AnnotationSet.from_dict(row) if row else None

    def list_annotation_sets(self, dataset_id: str | None = None) -> list[AnnotationSet]:
        query = "SELECT payload FROM annotation_sets"
        params: tuple[str, ...] = ()
        if dataset_id is not None:
            query += " WHERE dataset_id = ?"
            params = (dataset_id,)
        query += " ORDER BY id"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [AnnotationSet.from_dict(json.loads(row["payload"])) for row in rows]

    def save_review_decision(self, decision: ReviewDecision) -> ReviewDecision:
        payload = json.dumps(decision.to_dict(), ensure_ascii=False)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO review_decisions (id, target_id, payload)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  target_id=excluded.target_id,
                  payload=excluded.payload
                """,
                (decision.id, decision.target_id, payload),
            )
        return decision

    def save_export(self, export_id: str, annotation_set_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO exports (id, annotation_set_id, payload)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  annotation_set_id=excluded.annotation_set_id,
                  payload=excluded.payload
                """,
                (export_id, annotation_set_id, data),
            )
        return payload

    def get_export(self, export_id: str) -> dict[str, Any] | None:
        row = self._get("exports", export_id)
        return row

    def _upsert(self, table: str, row_id: str, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False)
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {table} (id, payload)
                VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload
                """,
                (row_id, data),
            )

    def _get(self, table: str, row_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(f"SELECT payload FROM {table} WHERE id = ?", (row_id,)).fetchone()
        return json.loads(row["payload"]) if row else None
