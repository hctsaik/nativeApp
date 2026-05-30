"""
tests/annotation/test_storage_workspace.py
-------------------------------------------
針對新三張表（system_tenants / tenant_user_mappings / annotation_tasks）
的 SQLiteMetadataStore 測試，以及 workspace 工作目錄管理測試。
"""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from plugins.labeling.domain.core.models import (
    Annotation,
    AnnotationSet,
    AnnotationTask,
    BBoxGeometry,
    LabelDef,
    LabelSchema,
    SystemTenant,
    TenantUserMapping,
    utc_now_iso,
)
from plugins.labeling.domain.storage.sqlite_store import SQLiteMetadataStore
from plugins.labeling.domain.storage.workspace import AnnotationWorkspace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _store(tmp_path: Path) -> SQLiteMetadataStore:
    return SQLiteMetadataStore(tmp_path / "catalog.sqlite")


def _tenant(system_name: str = "AOI-A") -> SystemTenant:
    return SystemTenant(
        tenant_id=str(uuid4()),
        system_name=system_name,
        server_host_name="https://aoi.internal",
        target_format="coco",
        created_at=utc_now_iso(),
    )


def _task(tenant_id: str, ant_id: str = "ANT_001", ant_active: int = 0) -> AnnotationTask:
    now = utc_now_iso()
    return AnnotationTask(
        task_id=str(uuid4()),
        tenant_id=tenant_id,
        ant_id=ant_id,
        ant_active=ant_active,
        annotation_json={"data": "test"},
        external_context={"lot_id": "L1"},
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# SystemTenant CRUD
# ---------------------------------------------------------------------------

def test_save_and_get_tenant(tmp_path: Path) -> None:
    store = _store(tmp_path)
    t = _tenant()
    store.save_tenant(t)
    fetched = store.get_tenant(t.tenant_id)
    assert fetched is not None
    assert fetched.tenant_id == t.tenant_id
    assert fetched.system_name == t.system_name
    assert fetched.target_format == t.target_format


def test_get_tenant_not_found(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.get_tenant("nonexistent") is None


def test_list_tenants(tmp_path: Path) -> None:
    store = _store(tmp_path)
    t1 = _tenant("A")
    t2 = _tenant("B")
    store.save_tenant(t1)
    store.save_tenant(t2)
    tenants = store.list_tenants()
    ids = {t.tenant_id for t in tenants}
    assert t1.tenant_id in ids
    assert t2.tenant_id in ids


def test_save_tenant_upsert(tmp_path: Path) -> None:
    store = _store(tmp_path)
    t = _tenant()
    store.save_tenant(t)
    t.system_name = "Updated-Name"
    store.save_tenant(t)
    fetched = store.get_tenant(t.tenant_id)
    assert fetched.system_name == "Updated-Name"


# ---------------------------------------------------------------------------
# TenantUserMapping
# ---------------------------------------------------------------------------

def test_add_and_list_user_mappings(tmp_path: Path) -> None:
    store = _store(tmp_path)
    t = _tenant()
    store.save_tenant(t)
    m1 = TenantUserMapping(id=str(uuid4()), tenant_id=t.tenant_id, user_id="emp001")
    m2 = TenantUserMapping(id=str(uuid4()), tenant_id=t.tenant_id, user_id="emp002")
    store.add_user_mapping(m1)
    store.add_user_mapping(m2)
    mappings = store.list_user_mappings(t.tenant_id)
    user_ids = {m.user_id for m in mappings}
    assert "emp001" in user_ids
    assert "emp002" in user_ids


def test_add_user_mapping_idempotent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    t = _tenant()
    store.save_tenant(t)
    m = TenantUserMapping(id=str(uuid4()), tenant_id=t.tenant_id, user_id="emp001")
    store.add_user_mapping(m)
    store.add_user_mapping(m)  # should not raise
    assert len(store.list_user_mappings(t.tenant_id)) == 1


def test_is_user_authorized(tmp_path: Path) -> None:
    store = _store(tmp_path)
    t = _tenant()
    store.save_tenant(t)
    m = TenantUserMapping(id=str(uuid4()), tenant_id=t.tenant_id, user_id="emp001")
    store.add_user_mapping(m)
    assert store.is_user_authorized(t.tenant_id, "emp001") is True
    assert store.is_user_authorized(t.tenant_id, "nobody") is False


# ---------------------------------------------------------------------------
# AnnotationTask CRUD
# ---------------------------------------------------------------------------

def test_save_and_get_task(tmp_path: Path) -> None:
    store = _store(tmp_path)
    t = _tenant()
    store.save_tenant(t)
    task = _task(t.tenant_id)
    store.save_task(task)
    fetched = store.get_task(task.task_id)
    assert fetched is not None
    assert fetched.task_id == task.task_id
    assert fetched.ant_id == task.ant_id
    assert fetched.annotation_json == task.annotation_json
    assert fetched.external_context == task.external_context


def test_get_task_not_found(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.get_task("nonexistent") is None


def test_save_task_upsert_updates_ant_active(tmp_path: Path) -> None:
    store = _store(tmp_path)
    t = _tenant()
    store.save_tenant(t)
    task = _task(t.tenant_id, ant_active=0)
    store.save_task(task)
    task.ant_active = 2
    task.annotated_by = "emp001"
    store.save_task(task)
    fetched = store.get_task(task.task_id)
    assert fetched.ant_active == 2
    assert fetched.annotated_by == "emp001"


def test_list_tasks_by_tenant(tmp_path: Path) -> None:
    store = _store(tmp_path)
    t = _tenant()
    store.save_tenant(t)
    task1 = _task(t.tenant_id, "ANT_001")
    task2 = _task(t.tenant_id, "ANT_002")
    store.save_task(task1)
    store.save_task(task2)
    tasks = store.list_tasks(t.tenant_id)
    ids = {tsk.task_id for tsk in tasks}
    assert task1.task_id in ids
    assert task2.task_id in ids


def test_list_tasks_filter_ant_active(tmp_path: Path) -> None:
    store = _store(tmp_path)
    t = _tenant()
    store.save_tenant(t)
    pending = _task(t.tenant_id, "ANT_001", ant_active=0)
    processing = _task(t.tenant_id, "ANT_002", ant_active=1)
    completed = _task(t.tenant_id, "ANT_003", ant_active=2)
    store.save_task(pending)
    store.save_task(processing)
    store.save_task(completed)
    assert len(store.list_tasks(t.tenant_id, ant_active=0)) == 1
    assert len(store.list_tasks(t.tenant_id, ant_active=1)) == 1
    assert len(store.list_tasks(t.tenant_id, ant_active=2)) == 1
    assert len(store.list_tasks(t.tenant_id)) == 3


def test_get_task_by_ant_id(tmp_path: Path) -> None:
    store = _store(tmp_path)
    t = _tenant()
    store.save_tenant(t)
    task = _task(t.tenant_id, "ANT_999")
    store.save_task(task)
    fetched = store.get_task_by_ant_id(t.tenant_id, "ANT_999")
    assert fetched is not None
    assert fetched.task_id == task.task_id


def test_get_task_by_ant_id_not_found(tmp_path: Path) -> None:
    store = _store(tmp_path)
    t = _tenant()
    store.save_tenant(t)
    assert store.get_task_by_ant_id(t.tenant_id, "MISSING") is None


# ---------------------------------------------------------------------------
# Workspace 目錄管理
# ---------------------------------------------------------------------------

def test_workspace_task_images_dir(tmp_path: Path) -> None:
    ws = AnnotationWorkspace(tmp_path / "ws")
    d = ws.ensure_task_images_dir("task-abc")
    assert d.exists()
    assert d == ws.task_images_dir("task-abc")


# ---------------------------------------------------------------------------
# 舊版 workspace 相容性（dataset / schema / annotation_set）
# ---------------------------------------------------------------------------

def _write_image(path: Path) -> None:
    Image.new("RGB", (32, 24), color=(120, 40, 80)).save(path)


def test_workspace_ingests_image_idempotently(tmp_path: Path) -> None:
    workspace = AnnotationWorkspace(tmp_path / "workspace")
    source = tmp_path / "dog.png"
    _write_image(source)
    dataset = workspace.create_dataset("animals", str(tmp_path))

    first = workspace.ingest_image(dataset.id, source)
    second = workspace.ingest_image(dataset.id, source)

    assert first.id == second.id
    assert first.width == 32
    assert first.height == 24
    assert len(workspace.metadata.list_assets(dataset.id)) == 1


def test_workspace_persists_schema_and_canonical_annotation_set(tmp_path: Path) -> None:
    workspace = AnnotationWorkspace(tmp_path / "workspace")
    dataset = workspace.create_dataset("animals", str(tmp_path))
    schema = workspace.save_schema(
        LabelSchema(
            id="schema_1",
            name="animals",
            labels=[LabelDef(id="dog", name="dog", allowed_geometry_types=["bbox"])],
        )
    )
    annotation_set = AnnotationSet(
        id="aset_1",
        dataset_id=dataset.id,
        schema_id=schema.id,
        annotations=[
            Annotation(
                asset_id="asset_1",
                label_id="dog",
                geometry=BBoxGeometry(x=1, y=2, width=3, height=4),
            )
        ],
    )

    canonical_path = workspace.write_canonical_annotation_set(annotation_set)
    stored = workspace.metadata.get_annotation_set(annotation_set.id)

    assert canonical_path.exists()
    assert stored is not None
    assert stored.annotations[0].geometry.to_dict()["type"] == "bbox"
    assert json.loads(canonical_path.read_text(encoding="utf-8"))["id"] == "aset_1"
