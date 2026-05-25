"""
tests/annotation/test_integration_profile.py
---------------------------------------------
Phase 4 整合層的單元測試：
- IntegrationProfile 的載入與驗證
- FakeConnector 的行為
- FileConnector 的基本資產解析
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from annotation.integrations.connectors.fake_connector import FakeConnector
from annotation.integrations.connectors.file_connector import FileConnector
from annotation.integrations.contracts import ExportPayload, PaginationToken
from annotation.integrations.profiles import load_profile, load_profile_from_file


# ---------------------------------------------------------------------------
# 測試用 fixture helpers
# ---------------------------------------------------------------------------

def _valid_profile_dict(**overrides) -> dict:
    """回傳一個包含所有必填欄位的合法 profile dict，可用 overrides 覆寫欄位。"""
    base = {
        "version": "1",
        "system_id": "test-system",
        "tenant_id": "tenant-001",
        "connector_type": "fake",
        "credential_ref": None,
        "format_policy": "warn_and_skip",
        "field_mapping": {},
        "schema_mapping": {},
    }
    base.update(overrides)
    return base


def _fake_connector() -> FakeConnector:
    """回傳預載兩個 fixture task 的 FakeConnector。"""
    tasks = [
        {"external_id": "task-001", "image_uri": "/data/img/001.jpg"},
        {"external_id": "task-002", "image_uri": "/data/img/002.jpg"},
    ]
    schema = {"labels": ["cat", "dog"]}
    return FakeConnector(tasks=tasks, schema=schema)


# ---------------------------------------------------------------------------
# IntegrationProfile — 正常載入
# ---------------------------------------------------------------------------

def test_load_valid_profile():
    """正確 load 一個有所有必填欄位的 profile dict，應成功建立 IntegrationProfile。"""
    data = _valid_profile_dict()
    profile = load_profile(data)

    assert profile.version == "1"
    assert profile.system_id == "test-system"
    assert profile.tenant_id == "tenant-001"
    assert profile.connector_type == "fake"
    assert profile.format_policy == "warn_and_skip"
    assert profile.credential_ref is None
    assert profile.field_mapping.external_task_id == "task_id"  # 預設值


# ---------------------------------------------------------------------------
# IntegrationProfile — 必填欄位缺失驗證
# ---------------------------------------------------------------------------

def test_load_profile_missing_system_id_raises():
    """system_id 缺失時應 raise ValueError。"""
    data = _valid_profile_dict()
    del data["system_id"]

    with pytest.raises(ValueError, match="system_id"):
        load_profile(data)


def test_load_profile_missing_tenant_id_raises():
    """tenant_id 缺失時應 raise ValueError。"""
    data = _valid_profile_dict()
    del data["tenant_id"]

    with pytest.raises(ValueError, match="tenant_id"):
        load_profile(data)


def test_load_profile_missing_version_raises():
    """version 缺失時應 raise ValueError。"""
    data = _valid_profile_dict()
    del data["version"]

    with pytest.raises(ValueError, match="version"):
        load_profile(data)


def test_load_profile_missing_connector_type_raises():
    """connector_type 缺失時應 raise ValueError。"""
    data = _valid_profile_dict()
    del data["connector_type"]

    with pytest.raises(ValueError, match="connector_type"):
        load_profile(data)


def test_load_profile_invalid_connector_type_raises():
    """不支援的 connector_type 應 raise ValueError。"""
    data = _valid_profile_dict(connector_type="unknown")

    with pytest.raises(ValueError, match="connector_type"):
        load_profile(data)


def test_load_profile_invalid_format_policy_raises():
    """不支援的 format_policy 應 raise ValueError。"""
    data = _valid_profile_dict(format_policy="silently_corrupt")

    with pytest.raises(ValueError, match="format_policy"):
        load_profile(data)


# ---------------------------------------------------------------------------
# IntegrationProfile — 從檔案載入
# ---------------------------------------------------------------------------

def test_load_profile_from_file(tmp_path: Path):
    """load_profile_from_file 應能從 JSON 檔案正確載入 profile。"""
    profile_data = _valid_profile_dict(system_id="file-system", tenant_id="t-file")
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps(profile_data), encoding="utf-8")

    profile = load_profile_from_file(profile_file)
    assert profile.system_id == "file-system"
    assert profile.tenant_id == "t-file"


def test_load_profile_from_file_not_found(tmp_path: Path):
    """檔案不存在時應 raise FileNotFoundError。"""
    with pytest.raises(FileNotFoundError):
        load_profile_from_file(tmp_path / "nonexistent.json")


# ---------------------------------------------------------------------------
# FakeConnector — list_tasks
# ---------------------------------------------------------------------------

def test_fake_connector_list_tasks():
    """FakeConnector.list_tasks 應回傳與初始化時相同數量的 task。"""
    connector = _fake_connector()
    tasks, next_token = connector.list_tasks(query={}, pagination_token=PaginationToken())

    assert len(tasks) == 2
    assert tasks[0].external_id == "task-001"
    assert tasks[1].external_id == "task-002"
    assert next_token.value is None  # 無更多頁


def test_fake_connector_list_tasks_image_uri():
    """list_tasks 回傳的 ExternalTask 應包含正確的 image_uri。"""
    connector = _fake_connector()
    tasks, _ = connector.list_tasks(query={}, pagination_token=PaginationToken())

    assert tasks[0].image_uri == "/data/img/001.jpg"


# ---------------------------------------------------------------------------
# FakeConnector — push_annotations 記錄呼叫
# ---------------------------------------------------------------------------

def test_fake_connector_push_records_call():
    """push_annotations 後 get_push_calls() 應記錄該次呼叫。"""
    connector = _fake_connector()
    payload = ExportPayload(
        format_id="coco_json",
        data={"annotations": []},
        conversion_report={},
    )
    result = connector.push_annotations("task-001", payload, mode="upsert")

    assert result.success is True
    assert result.rows_written == 1

    calls = connector.get_push_calls()
    assert len(calls) == 1
    assert calls[0]["task_id"] == "task-001"
    assert calls[0]["format_id"] == "coco_json"
    assert calls[0]["mode"] == "upsert"


def test_fake_connector_push_accumulates_calls():
    """多次 push_annotations 應累積所有呼叫記錄。"""
    connector = _fake_connector()
    payload = ExportPayload(format_id="yolo", data={}, conversion_report={})

    connector.push_annotations("task-001", payload, mode="append")
    connector.push_annotations("task-002", payload, mode="append")

    assert len(connector.get_push_calls()) == 2


# ---------------------------------------------------------------------------
# FakeConnector — health_check
# ---------------------------------------------------------------------------

def test_fake_connector_health_is_connected():
    """FakeConnector.health_check 應永遠回傳 connected=True。"""
    connector = _fake_connector()
    health = connector.health_check()

    assert health.connected is True
    assert health.latency_ms == 0
    assert health.error is None


# ---------------------------------------------------------------------------
# FakeConnector — load_label_schema
# ---------------------------------------------------------------------------

def test_fake_connector_load_label_schema():
    """load_label_schema 應回傳 fixture schema，source_format 為 'fake'。"""
    connector = _fake_connector()
    schema = connector.load_label_schema()

    assert schema.source_format == "fake"
    assert schema.raw == {"labels": ["cat", "dog"]}


# ---------------------------------------------------------------------------
# FakeConnector — resolve_asset
# ---------------------------------------------------------------------------

def test_fake_connector_resolve_asset():
    """resolve_asset 應回傳 local_path 類型，value 等於 task.image_uri。"""
    from annotation.integrations.contracts import ExternalTask

    connector = _fake_connector()
    task = ExternalTask(external_id="t1", image_uri="/some/path/image.jpg")
    asset = connector.resolve_asset(task)

    assert asset.asset_type == "local_path"
    assert asset.value == "/some/path/image.jpg"


# ---------------------------------------------------------------------------
# FileConnector — resolve_asset（有效路徑）
# ---------------------------------------------------------------------------

def test_file_connector_resolve_existing_path(tmp_path: Path):
    """FileConnector.resolve_asset：有效本地路徑應回傳 ResolvedAsset(local_path)。"""
    from annotation.integrations.contracts import ExternalTask

    # 建立真實圖片檔（內容不重要，只需存在）
    img_file = tmp_path / "sample.jpg"
    img_file.write_bytes(b"\xff\xd8\xff")  # JPEG magic bytes

    profile_data = _valid_profile_dict(
        connector_type="file",
        image_root_path=str(tmp_path),
    )
    profile = load_profile(profile_data)
    connector = FileConnector(profile)

    task = ExternalTask(external_id="sample.jpg", image_uri=str(img_file))
    asset = connector.resolve_asset(task)

    assert asset.asset_type == "local_path"
    assert Path(asset.value).exists()


def test_file_connector_resolve_nonexistent_path(tmp_path: Path):
    """FileConnector.resolve_asset：路徑不存在應 raise FileNotFoundError。"""
    from annotation.integrations.contracts import ExternalTask

    profile_data = _valid_profile_dict(connector_type="file")
    profile = load_profile(profile_data)
    connector = FileConnector(profile)

    task = ExternalTask(
        external_id="ghost.jpg",
        image_uri=str(tmp_path / "does_not_exist.jpg"),
    )
    with pytest.raises(FileNotFoundError):
        connector.resolve_asset(task)


# ---------------------------------------------------------------------------
# FileConnector — list_tasks
# ---------------------------------------------------------------------------

def test_file_connector_list_tasks(tmp_path: Path):
    """FileConnector.list_tasks 應掃描目錄並回傳圖片 task 清單。"""
    # 建立測試圖片（2 張）
    (tmp_path / "a.jpg").write_bytes(b"\xff\xd8\xff")
    (tmp_path / "b.png").write_bytes(b"\x89PNG")
    (tmp_path / "readme.txt").write_text("not an image")

    profile_data = _valid_profile_dict(
        connector_type="file",
        image_root_path=str(tmp_path),
    )
    profile = load_profile(profile_data)
    connector = FileConnector(profile)

    tasks, next_token = connector.list_tasks(query={}, pagination_token=PaginationToken())

    assert len(tasks) == 2
    assert next_token.value is None
    external_ids = {t.external_id for t in tasks}
    assert "a.jpg" in external_ids
    assert "b.png" in external_ids


# ---------------------------------------------------------------------------
# FileConnector — load_label_schema
# ---------------------------------------------------------------------------

def test_file_connector_load_label_schema(tmp_path: Path):
    """FileConnector.load_label_schema 應讀取 label_file 並回傳 label 清單。"""
    label_file = tmp_path / "labels.txt"
    label_file.write_text("cat\ndog\n# comment\n\nbike\n", encoding="utf-8")

    profile_data = _valid_profile_dict(
        connector_type="file",
        label_file=str(label_file),
    )
    profile = load_profile(profile_data)
    connector = FileConnector(profile)

    schema = connector.load_label_schema()

    assert schema.source_format == "txt_label_list"
    assert schema.raw["labels"] == ["cat", "dog", "bike"]  # 空行與註解已過濾


# ---------------------------------------------------------------------------
# FileConnector — push_annotations
# ---------------------------------------------------------------------------

def test_file_connector_push_annotations(tmp_path: Path):
    """FileConnector.push_annotations 應將結果寫入 output_path 目錄。"""
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    profile_data = _valid_profile_dict(
        connector_type="file",
        output_path=str(output_dir),
    )
    profile = load_profile(profile_data)
    connector = FileConnector(profile)

    payload = ExportPayload(
        format_id="coco_json",
        data={"boxes": [{"x": 10, "y": 20}]},
        conversion_report={"warnings": 0},
    )
    result = connector.push_annotations("task-001", payload, mode="upsert")

    assert result.success is True
    assert result.rows_written == 1

    # 驗證檔案實際被寫出
    written_files = list(output_dir.glob("*.json"))
    assert len(written_files) == 1
    content = json.loads(written_files[0].read_text(encoding="utf-8"))
    assert content["task_id"] == "task-001"


# ---------------------------------------------------------------------------
# FileConnector — health_check
# ---------------------------------------------------------------------------

def test_file_connector_health_check_connected(tmp_path: Path):
    """image_root_path 存在時 health_check 應回傳 connected=True。"""
    profile_data = _valid_profile_dict(
        connector_type="file",
        image_root_path=str(tmp_path),
    )
    profile = load_profile(profile_data)
    connector = FileConnector(profile)

    health = connector.health_check()
    assert health.connected is True


def test_file_connector_health_check_disconnected(tmp_path: Path):
    """image_root_path 不存在時 health_check 應回傳 connected=False。"""
    missing_path = tmp_path / "nonexistent_root"

    profile_data = _valid_profile_dict(
        connector_type="file",
        image_root_path=str(missing_path),
    )
    profile = load_profile(profile_data)
    connector = FileConnector(profile)

    health = connector.health_check()
    assert health.connected is False
    assert health.error is not None
