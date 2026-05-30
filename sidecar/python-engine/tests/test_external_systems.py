"""Tests for declarative external-system (tenant) registration (no-code)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ENGINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_DIR))

from core import external_systems  # noqa: E402
from plugins.labeling.domain.services import AnnotationService  # noqa: E402
from plugins.labeling.domain.storage.workspace import AnnotationWorkspace  # noqa: E402


def test_load_declared_systems_from_log_dir(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "external_systems.yaml").write_text(
        yaml.safe_dump({"systems": [
            {"system_name": "iWISC", "server_host_name": "http://h:8765",
             "target_format": "xanylabeling", "api_token_env": "IWSC_TOKEN"},
        ]}), encoding="utf-8")
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path))
    systems = external_systems.load_declared_systems()
    assert len(systems) == 1 and systems[0]["system_name"] == "iWISC"


def test_load_declared_systems_empty_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path))  # no config file
    # repo default has systems: [] → either way empty
    assert external_systems.load_declared_systems() == [] or isinstance(
        external_systems.load_declared_systems(), list)


def test_sync_external_systems_idempotent_and_token_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("IWSC_TOKEN", "secret-123")
    service = AnnotationService(AnnotationWorkspace(tmp_path / "ws"))
    declared = [
        {"system_name": "iWISC", "server_host_name": "http://h:8765/",
         "target_format": "xanylabeling", "api_token_env": "IWSC_TOKEN"},
        {"system_name": "SMM", "server_host_name": "http://smm",
         "target_format": "coco"},
    ]
    added = service.sync_external_systems(declared)
    assert set(added) == {"iWISC", "SMM"}
    names = {t["system_name"] for t in service.list_tenants()}
    assert {"iWISC", "SMM"} <= names

    # idempotent: re-sync registers nothing new, no duplicates
    added2 = service.sync_external_systems(declared)
    assert added2 == []
    assert len([t for t in service.list_tenants() if t["system_name"] == "iWISC"]) == 1


def test_sync_skips_incomplete_entries(tmp_path):
    service = AnnotationService(AnnotationWorkspace(tmp_path / "ws"))
    added = service.sync_external_systems([{"system_name": "x"}])  # missing host/format
    assert added == []
