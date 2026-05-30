from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from plugins.labeling.domain.core.models import (
    AnnotationSet,
    AnnotationTask,
    Dataset,
    ImageAsset,
    LabelSchema,
    ReviewDecision,
    SystemTenant,
    TenantUserMapping,
)


class SQLiteMetadataStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;

                -- 新工業標注平台三張表
                CREATE TABLE IF NOT EXISTS system_tenants (
                    tenant_id   TEXT PRIMARY KEY,
                    system_name TEXT UNIQUE NOT NULL,
                    server_host_name TEXT NOT NULL,
                    target_format TEXT NOT NULL,
                    api_token   TEXT,
                    created_at  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tenant_user_mappings (
                    id          TEXT PRIMARY KEY,
                    tenant_id   TEXT NOT NULL,
                    user_id     TEXT NOT NULL,
                    ant_id      TEXT,
                    UNIQUE(tenant_id, ant_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS annotation_tasks (
                    task_id                 TEXT PRIMARY KEY,
                    tenant_id               TEXT NOT NULL,
                    ant_id                  TEXT NOT NULL,
                    ant_active              INTEGER NOT NULL DEFAULT 0,
                    original_classification TEXT,
                    new_classification      TEXT,
                    annotation_json         TEXT NOT NULL DEFAULT '{}',
                    external_context        TEXT NOT NULL DEFAULT '{}',
                    annotated_by            TEXT,
                    created_at              TEXT NOT NULL,
                    updated_at              TEXT NOT NULL,
                    UNIQUE(tenant_id, ant_id)
                );

                -- 保留舊表以供 FormatRegistry / dry-run 測試使用
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
            # 遷移舊資料庫：delivery_status 欄位若不存在則新增
            for _col_ddl in [
                "ALTER TABLE annotation_tasks ADD COLUMN delivery_status TEXT",
                "ALTER TABLE annotation_tasks ADD COLUMN original_annotation_json TEXT NOT NULL DEFAULT '{}'",
                "ALTER TABLE system_tenants ADD COLUMN connector_type TEXT",
                "ALTER TABLE system_tenants ADD COLUMN connector_config TEXT",
            ]:
                try:
                    conn.execute(_col_ddl)
                    conn.commit()
                except Exception:
                    pass

            # 遷移 tenant_user_mappings：舊版無 ant_id 欄位，需重建以加入新 UNIQUE 約束
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(tenant_user_mappings)").fetchall()}
            if "ant_id" not in cols:
                conn.executescript("""
                    CREATE TABLE _tenant_user_mappings_new (
                        id        TEXT PRIMARY KEY,
                        tenant_id TEXT NOT NULL,
                        user_id   TEXT NOT NULL,
                        ant_id    TEXT,
                        UNIQUE(tenant_id, ant_id, user_id)
                    );
                    INSERT OR IGNORE INTO _tenant_user_mappings_new (id, tenant_id, user_id, ant_id)
                        SELECT id, tenant_id, user_id, NULL FROM tenant_user_mappings;
                    DROP TABLE tenant_user_mappings;
                    ALTER TABLE _tenant_user_mappings_new RENAME TO tenant_user_mappings;
                """)

    # ── SystemTenant ─────────────────────────────────────────────────────────

    def save_tenant(self, tenant: SystemTenant) -> SystemTenant:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO system_tenants
                    (tenant_id, system_name, server_host_name, target_format, api_token,
                     created_at, connector_type, connector_config)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id) DO UPDATE SET
                    system_name=excluded.system_name,
                    server_host_name=excluded.server_host_name,
                    target_format=excluded.target_format,
                    api_token=excluded.api_token,
                    connector_type=excluded.connector_type,
                    connector_config=excluded.connector_config
                """,
                (
                    tenant.tenant_id,
                    tenant.system_name,
                    tenant.server_host_name,
                    tenant.target_format,
                    tenant.api_token,
                    tenant.created_at,
                    tenant.connector_type,
                    json.dumps(tenant.connector_config, ensure_ascii=False)
                    if tenant.connector_config else None,
                ),
            )
        return tenant

    def get_tenant(self, tenant_id: str) -> SystemTenant | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM system_tenants WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()
        return _row_to_tenant(row) if row else None

    def list_tenants(self) -> list[SystemTenant]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM system_tenants ORDER BY system_name"
            ).fetchall()
        return [_row_to_tenant(row) for row in rows]

    def delete_tenant(self, tenant_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM tenant_user_mappings WHERE tenant_id = ?", (tenant_id,)
            )
            conn.execute(
                "DELETE FROM annotation_tasks WHERE tenant_id = ?", (tenant_id,)
            )
            conn.execute(
                "DELETE FROM system_tenants WHERE tenant_id = ?", (tenant_id,)
            )

    # ── TenantUserMapping ─────────────────────────────────────────────────────

    def add_user_mapping(self, mapping: TenantUserMapping) -> TenantUserMapping:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO tenant_user_mappings (id, tenant_id, user_id, ant_id)
                VALUES (?, ?, ?, ?)
                """,
                (mapping.id, mapping.tenant_id, mapping.user_id, mapping.ant_id),
            )
        return mapping

    def list_user_mappings(self, tenant_id: str, ant_id: str | None = None) -> list[TenantUserMapping]:
        with self.connect() as conn:
            if ant_id is None:
                rows = conn.execute(
                    "SELECT * FROM tenant_user_mappings WHERE tenant_id = ? AND ant_id IS NULL ORDER BY user_id",
                    (tenant_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tenant_user_mappings WHERE tenant_id = ? AND ant_id = ? ORDER BY user_id",
                    (tenant_id, ant_id),
                ).fetchall()
        return [
            TenantUserMapping(id=row["id"], tenant_id=row["tenant_id"], user_id=row["user_id"], ant_id=row["ant_id"])
            for row in rows
        ]

    def list_all_user_mappings(self, tenant_id: str) -> list[TenantUserMapping]:
        """回傳該 tenant 下所有授權記錄（含系統層級與各任務層級）。"""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tenant_user_mappings WHERE tenant_id = ? ORDER BY ant_id, user_id",
                (tenant_id,),
            ).fetchall()
        return [
            TenantUserMapping(id=row["id"], tenant_id=row["tenant_id"], user_id=row["user_id"], ant_id=row["ant_id"])
            for row in rows
        ]

    def remove_user_mapping(self, tenant_id: str, user_id: str, ant_id: str | None = None) -> None:
        with self.connect() as conn:
            if ant_id is None:
                conn.execute(
                    "DELETE FROM tenant_user_mappings WHERE tenant_id = ? AND user_id = ? AND ant_id IS NULL",
                    (tenant_id, user_id),
                )
            else:
                conn.execute(
                    "DELETE FROM tenant_user_mappings WHERE tenant_id = ? AND user_id = ? AND ant_id = ?",
                    (tenant_id, user_id, ant_id),
                )

    def is_user_authorized(self, tenant_id: str, user_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM tenant_user_mappings WHERE tenant_id = ? AND user_id = ? AND ant_id IS NULL",
                (tenant_id, user_id),
            ).fetchone()
        return row is not None

    # ── AnnotationTask ────────────────────────────────────────────────────────

    def save_task(self, task: AnnotationTask) -> AnnotationTask:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO annotation_tasks
                    (task_id, tenant_id, ant_id, ant_active,
                     original_classification, new_classification,
                     annotation_json, original_annotation_json, external_context,
                     annotated_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    ant_active=excluded.ant_active,
                    original_classification=excluded.original_classification,
                    new_classification=excluded.new_classification,
                    annotation_json=excluded.annotation_json,
                    external_context=excluded.external_context,
                    annotated_by=excluded.annotated_by,
                    updated_at=excluded.updated_at
                """,
                (
                    task.task_id,
                    task.tenant_id,
                    task.ant_id,
                    task.ant_active,
                    task.original_classification,
                    task.new_classification,
                    json.dumps(task.annotation_json, ensure_ascii=False),
                    json.dumps(task.original_annotation_json, ensure_ascii=False),
                    json.dumps(task.external_context, ensure_ascii=False),
                    task.annotated_by,
                    task.created_at,
                    task.updated_at,
                ),
            )
        return task

    def get_task(self, task_id: str) -> AnnotationTask | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM annotation_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        return _row_to_task(row) if row else None

    def list_tasks(self, tenant_id: str, ant_active: int | None = None) -> list[AnnotationTask]:
        if ant_active is None:
            query = "SELECT * FROM annotation_tasks WHERE tenant_id = ? ORDER BY created_at"
            params: tuple = (tenant_id,)
        else:
            query = "SELECT * FROM annotation_tasks WHERE tenant_id = ? AND ant_active = ? ORDER BY created_at"
            params = (tenant_id, ant_active)
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_task(row) for row in rows]

    def get_task_by_ant_id(self, tenant_id: str, ant_id: str) -> AnnotationTask | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM annotation_tasks WHERE tenant_id = ? AND ant_id = ?",
                (tenant_id, ant_id),
            ).fetchone()
        return _row_to_task(row) if row else None

    def update_task_delivery(self, task_id: str, delivery_result: dict[str, Any]) -> None:
        """將回饋結果（delivery_result）序列化後存入 delivery_status 欄位。"""
        with self.connect() as conn:
            conn.execute(
                "UPDATE annotation_tasks SET delivery_status = ? WHERE task_id = ?",
                (json.dumps(delivery_result, ensure_ascii=False), task_id),
            )

    # ── Legacy Dataset / Asset / Schema / AnnotationSet ──────────────────────
    # 保留以供 FormatRegistry 與 dry-run 測試使用

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
        params: tuple = ()
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

    # ── Private helpers ───────────────────────────────────────────────────────

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


# ── Row helpers ───────────────────────────────────────────────────────────────

def _row_to_tenant(row: sqlite3.Row) -> SystemTenant:
    keys = row.keys()
    return SystemTenant(
        tenant_id=row["tenant_id"],
        system_name=row["system_name"],
        server_host_name=row["server_host_name"],
        target_format=row["target_format"],
        api_token=row["api_token"],
        created_at=row["created_at"],
        connector_type=row["connector_type"] if "connector_type" in keys else None,
        connector_config=(
            json.loads(row["connector_config"])
            if "connector_config" in keys and row["connector_config"] else None
        ),
    )


def _row_to_task(row: sqlite3.Row) -> AnnotationTask:
    keys = row.keys()
    raw_delivery = row["delivery_status"] if "delivery_status" in keys else None
    raw_orig_ant = row["original_annotation_json"] if "original_annotation_json" in keys else None
    return AnnotationTask(
        task_id=row["task_id"],
        tenant_id=row["tenant_id"],
        ant_id=row["ant_id"],
        ant_active=row["ant_active"],
        original_classification=row["original_classification"],
        new_classification=row["new_classification"],
        annotation_json=json.loads(row["annotation_json"]),
        original_annotation_json=json.loads(raw_orig_ant) if raw_orig_ant else {},
        external_context=json.loads(row["external_context"]),
        annotated_by=row["annotated_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        delivery_status=json.loads(raw_delivery) if raw_delivery else None,
    )
