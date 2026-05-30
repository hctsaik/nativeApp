"""
tests/annotation/test_services.py
----------------------------------
針對新工業標注平台 API 的服務層測試。
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from plugins.labeling.domain.core.errors import ConflictError, NotFoundError
from plugins.labeling.domain.services import AnnotationService
from plugins.labeling.domain.storage.workspace import AnnotationWorkspace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_image(path: Path) -> None:
    Image.new("RGB", (100, 80), color=(1, 2, 3)).save(path)


def _service(tmp_path: Path) -> AnnotationService:
    return AnnotationService(AnnotationWorkspace(tmp_path / "workspace"))


def _register_tenant(service: AnnotationService, suffix: str = "A") -> str:
    result = service.register_tenant(
        system_name=f"AOI-System-{suffix}",
        server_host_name="fake://local",
        target_format="coco",
    )
    return result["tenant_id"]


# ---------------------------------------------------------------------------
# Phase 0: Tenant 管理
# ---------------------------------------------------------------------------

def test_register_and_list_tenants(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    t1 = svc.register_tenant("System-A", "fake://host-a", "coco")
    t2 = svc.register_tenant("System-B", "fake://host-b", "yolo-detection", api_token="tok")

    tenants = svc.list_tenants()
    ids = {t["tenant_id"] for t in tenants}
    assert t1["tenant_id"] in ids
    assert t2["tenant_id"] in ids
    assert t2["api_token"] == "tok"


def test_get_tenant(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    created = svc.register_tenant("Sys", "fake://x", "coco")
    fetched = svc.get_tenant(created["tenant_id"])
    assert fetched["system_name"] == "Sys"


def test_get_tenant_not_found(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    with pytest.raises(NotFoundError):
        svc.get_tenant("nonexistent-id")


def test_register_tenant_strips_trailing_slash(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    t = svc.register_tenant("S", "fake://host/", "coco")
    assert not t["server_host_name"].endswith("/")


def test_add_and_list_users(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tid = _register_tenant(svc)
    svc.add_user_to_tenant(tid, "emp001")
    svc.add_user_to_tenant(tid, "emp002")
    users = svc.list_tenant_users(tid)
    user_ids = {u["user_id"] for u in users}
    assert "emp001" in user_ids
    assert "emp002" in user_ids


def test_is_user_authorized(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tid = _register_tenant(svc)
    svc.add_user_to_tenant(tid, "emp001")
    assert svc.workspace.metadata.is_user_authorized(tid, "emp001") is True
    assert svc.workspace.metadata.is_user_authorized(tid, "nobody") is False


# ---------------------------------------------------------------------------
# Phase 1: 任務發現（FakeConnector）
# ---------------------------------------------------------------------------

def test_get_ant_list_returns_empty_for_fake_connector(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tid = _register_tenant(svc)
    result = svc.get_ant_list(tid)
    # FakeConnector 預設 tasks=[] 所以回傳空陣列
    assert isinstance(result, list)


def test_get_ant_list_tenant_not_found(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    with pytest.raises(NotFoundError):
        svc.get_ant_list("bad-tenant")


# ---------------------------------------------------------------------------
# Phase 2: 任務操作（不透過外部 ZIP 下載）
# ---------------------------------------------------------------------------

def _seed_task(svc: AnnotationService, tmp_path: Path) -> tuple[str, str]:
    """直接向 DB 寫入一筆 AnnotationTask（繞過 claim_task 的 ZIP 下載流程）。"""
    from plugins.labeling.domain.core.models import AnnotationTask, utc_now_iso
    from uuid import uuid4
    tid = _register_tenant(svc)
    task_id = str(uuid4())
    now = utc_now_iso()
    task = AnnotationTask(
        task_id=task_id,
        tenant_id=tid,
        ant_id="ANT_001",
        ant_active=1,
        annotation_json={"dummy": True},
        external_context={"lot_id": "L1"},
        annotated_by="emp001",
        created_at=now,
        updated_at=now,
    )
    svc.workspace.metadata.save_task(task)
    return tid, task_id


def test_concurrent_claim_blocked_by_unique(tmp_path: Path) -> None:
    """原子認領：DB 對 (tenant_id, ant_id) 的 UNIQUE 約束擋下第二位認領者
    （即使 task_id 不同）。這是 claim_task 本地併發競態防護的基礎。"""
    from uuid import uuid4
    from plugins.labeling.domain.core.models import AnnotationTask, utc_now_iso
    svc = _service(tmp_path)
    tid, _ = _seed_task(svc, tmp_path)  # 已有 (tid, ANT_001)
    dup = AnnotationTask(
        task_id=str(uuid4()),            # 不同 task_id
        tenant_id=tid, ant_id="ANT_001",  # 相同 (tenant_id, ant_id)
        ant_active=1, annotated_by="emp999",
        created_at=utc_now_iso(), updated_at=utc_now_iso(),
    )
    with pytest.raises(Exception) as exc:
        svc.workspace.metadata.save_task(dup)
    assert "unique" in str(exc.value).lower()


def test_get_task(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tid, task_id = _seed_task(svc, tmp_path)
    result = svc.get_task(task_id)
    assert result["task_id"] == task_id
    assert result["ant_id"] == "ANT_001"


def test_get_task_not_found(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    with pytest.raises(NotFoundError):
        svc.get_task("no-such-task")


def test_save_annotation_updates_annotation_json(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tid, task_id = _seed_task(svc, tmp_path)
    new_ant = {"images": [], "annotations": [], "categories": []}
    result = svc.save_annotation(task_id, new_ant, new_classification="OK", annotated_by="emp002")
    assert result["annotation_json"] == new_ant
    assert result["new_classification"] == "OK"
    assert result["annotated_by"] == "emp002"


def test_complete_task_sets_ant_active_2(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tid, task_id = _seed_task(svc, tmp_path)
    result = svc.complete_task(task_id, annotated_by="emp001")
    assert result["ant_active"] == 2


def test_list_tasks_by_tenant(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tid, task_id = _seed_task(svc, tmp_path)
    tasks = svc.list_tasks(tid)
    assert any(t["task_id"] == task_id for t in tasks)


def test_list_tasks_filter_by_ant_active(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tid, task_id = _seed_task(svc, tmp_path)
    svc.complete_task(task_id, annotated_by="emp001")
    pending = svc.list_tasks(tid, ant_active=0)
    completed = svc.list_tasks(tid, ant_active=2)
    assert all(t["ant_active"] == 0 for t in pending)
    assert any(t["task_id"] == task_id for t in completed)


def test_list_tasks_filter_by_user(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tid, task_id = _seed_task(svc, tmp_path)
    by_user = svc.list_tasks(tid, user_id="emp001")
    by_other = svc.list_tasks(tid, user_id="nobody")
    assert any(t["task_id"] == task_id for t in by_user)
    assert by_other == []


# ---------------------------------------------------------------------------
# Phase 3: Dashboard stats & export ZIP
# ---------------------------------------------------------------------------

def test_dashboard_stats(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tid, task_id = _seed_task(svc, tmp_path)
    stats = svc.get_dashboard_stats(tid)
    assert stats["tenant_id"] == tid
    assert stats["total"] == 1
    assert stats["processing"] == 1


def test_export_result_zip_returns_bytes(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tid, task_id = _seed_task(svc, tmp_path)
    raw = svc.export_result_zip(task_id, "orig_img_orig_ant")
    assert isinstance(raw, bytes)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = zf.namelist()
    assert "annotations.json" in names
    assert "annotated_by.txt" in names


def test_export_result_zip_invalid_mode(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    tid, task_id = _seed_task(svc, tmp_path)
    with pytest.raises(ValueError):
        svc.export_result_zip(task_id, "invalid_mode")


# ---------------------------------------------------------------------------
# 舊版 FormatRegistry 相容性測試（保留）
# ---------------------------------------------------------------------------

def _seed_legacy(service: AnnotationService, tmp_path: Path):
    """建立 dataset / asset / schema / annotation_set（舊版流程）。"""
    image_path = tmp_path / "dog.png"
    _write_image(image_path)
    dataset = service.create_dataset("animals", str(tmp_path))
    asset = service.ingest_assets(dataset["id"], [str(image_path)])["assets"][0]
    schema = service.create_schema(
        "animals",
        [{"id": "dog", "name": "dog", "allowed_geometry_types": ["bbox"]}],
        schema_id="schema_1",
    )
    annotation_set = service.create_annotation_set(
        dataset["id"],
        schema["id"],
        [
            {
                "asset_id": asset["id"],
                "label_id": "dog",
                "geometry": {"type": "bbox", "x": 10, "y": 20, "width": 30, "height": 40},
            }
        ],
    )
    return dataset["id"], asset["id"], schema["id"], annotation_set["id"]


def test_service_review_approval_blocks_later_overwrite(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _, asset_id, _, annotation_set_id = _seed_legacy(service, tmp_path)
    service.submit_for_review(annotation_set_id)
    service.review_task(annotation_set_id, "approved", actor_id="reviewer")
    with pytest.raises(ConflictError):
        service.upsert_annotations(
            annotation_set_id,
            [
                {
                    "asset_id": asset_id,
                    "label_id": "dog",
                    "geometry": {"type": "bbox", "x": 1, "y": 2, "width": 3, "height": 4},
                }
            ],
        )


def test_training_export_requires_approved_annotation_set(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _, _, _, annotation_set_id = _seed_legacy(service, tmp_path)
    with pytest.raises(ConflictError):
        service.create_export(annotation_set_id, "yolo-detection", str(tmp_path / "yolo"), purpose="training")
    service.submit_for_review(annotation_set_id)
    service.review_task(annotation_set_id, "approved", actor_id="reviewer")
    result = service.create_export(annotation_set_id, "yolo-detection", str(tmp_path / "yolo"), purpose="training")
    assert result["format"] == "yolo-detection"
    assert result["conversion_report"]["lossless"] is True
    assert service.get_export(result["export_id"])["export_id"] == result["export_id"]


def test_service_lists_supported_annotation_formats(tmp_path: Path) -> None:
    service = _service(tmp_path)
    formats = service.supported_annotation_formats()
    by_id = {item["id"]: item for item in formats}
    assert by_id["labelme"]["can_import"] is True
    assert by_id["x-anylabeling"]["can_export"] is True
    assert by_id["isat"]["can_import"] is True
    assert by_id["coco"]["can_import"] is True
    assert by_id["yolo-segmentation"]["can_export"] is True


def test_service_detect_xanylabeling_shape(tmp_path: Path) -> None:
    service = _service(tmp_path)
    install = service.detect_xanylabeling()
    assert "available" in install
    assert "message" in install
