from __future__ import annotations

import importlib.util
import io
import json
import sys
import types
import zipfile
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent


def _load(cim_log: Path):
    """Load 019_process with CIM_LOG_DIR pre-set via env (must call after monkeypatch)."""
    spec = importlib.util.spec_from_file_location("_019_proc", _HERE / "019_process.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_zip(items: list[dict], annotations: dict[str, bytes] | None = None,
              images: list[str] | None = None) -> bytes:
    """Build an in-memory zip with manifest.json + optional images/ and annotations/."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        manifest = {"items": items}
        zf.writestr("manifest.json", json.dumps(manifest))
        for fname in (images or []):
            zf.writestr(f"images/{fname}", b"img")
        for fname, content in (annotations or {}).items():
            zf.writestr(f"annotations/{fname}", content)
    return buf.getvalue()


# ─── _extract_zip ─────────────────────────────────────────────────────────────

def test_extract_zip_reads_manifest_items(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(tmp_path / "cim_log")
    items = [{"file_name": "a.jpg", "metadata": {}}, {"file_name": "b.jpg", "metadata": {}}]
    zip_bytes = _make_zip(items, images=["a.jpg", "b.jpg"])
    zip_path = tmp_path / "pkg.zip"
    zip_path.write_bytes(zip_bytes)
    target = tmp_path / "out"

    result = proc._extract_zip(zip_path, target)
    assert len(result["manifest_items"]) == 2
    assert result["manifest_items"][0]["file_name"] == "a.jpg"
    assert (target / "a.jpg").exists()
    assert (target / "b.jpg").exists()


def test_extract_zip_extracts_annotations(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(tmp_path / "cim_log")
    ann_json = json.dumps({"shapes": [{"label": "cat"}]}).encode()
    zip_bytes = _make_zip(
        [{"file_name": "a.jpg", "metadata": {}}],
        images=["a.jpg"],
        annotations={"a.json": ann_json},
    )
    zip_path = tmp_path / "pkg.zip"
    zip_path.write_bytes(zip_bytes)
    target = tmp_path / "out"

    proc._extract_zip(zip_path, target)
    ann = target / "a.json"
    assert ann.exists()
    data = json.loads(ann.read_text("utf-8"))
    assert data["shapes"][0]["label"] == "cat"


def test_extract_zip_conflict_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(tmp_path / "cim_log")
    zip_bytes = _make_zip([], annotations={"a.json": b"{}"})
    zip_path = tmp_path / "pkg.zip"
    zip_path.write_bytes(zip_bytes)
    target = tmp_path / "out"
    target.mkdir()
    (target / "a.json").write_text("{}", encoding="utf-8")  # pre-existing → conflict

    result = proc._extract_zip(zip_path, target)
    assert "a.json" in result["conflicts"]


def test_extract_zip_no_manifest_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(tmp_path / "cim_log")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("images/a.jpg", b"img")
    zip_path = tmp_path / "pkg.zip"
    zip_path.write_bytes(buf.getvalue())
    target = tmp_path / "out"

    result = proc._extract_zip(zip_path, target)
    assert result["manifest_items"] == []
    assert (target / "a.jpg").exists()


# ─── _scan_annotation_status ──────────────────────────────────────────────────

def test_scan_annotation_status_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(tmp_path / "cim_log")
    items = [{"file_name": "a.jpg", "metadata": {}}]
    result = proc._scan_annotation_status(tmp_path, items)
    assert len(result) == 1
    assert result[0]["status"] == "empty"


def test_scan_annotation_status_needs_review(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(tmp_path / "cim_log")
    ann = {"shapes": [{"label": "cat"}], "flags": {}}
    (tmp_path / "a.json").write_text(json.dumps(ann), encoding="utf-8")
    items = [{"file_name": "a.jpg", "metadata": {}}]
    result = proc._scan_annotation_status(tmp_path, items)
    assert result[0]["status"] == "needs_review"


def test_scan_annotation_status_classification_needs_review(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(tmp_path / "cim_log")
    ann = {"shapes": [], "flags": {"classification": "dog"}}
    (tmp_path / "a.json").write_text(json.dumps(ann), encoding="utf-8")
    items = [{"file_name": "a.jpg", "metadata": {}}]
    result = proc._scan_annotation_status(tmp_path, items)
    assert result[0]["status"] == "needs_review"


def test_scan_annotation_status_empty_json(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(tmp_path / "cim_log")
    (tmp_path / "a.json").write_text(json.dumps({"shapes": [], "flags": {}}), encoding="utf-8")
    items = [{"file_name": "a.jpg", "metadata": {}}]
    result = proc._scan_annotation_status(tmp_path, items)
    assert result[0]["status"] == "empty"


def test_scan_annotation_status_mixed(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(tmp_path / "cim_log")
    (tmp_path / "b.json").write_text(json.dumps({"shapes": [{"label": "cat"}]}), encoding="utf-8")
    items = [
        {"file_name": "a.jpg", "metadata": {}},   # no json → empty
        {"file_name": "b.jpg", "metadata": {}},   # has shapes → needs_review
    ]
    result = proc._scan_annotation_status(tmp_path, items)
    statuses = {r["file_name"]: r["status"] for r in result}
    assert statuses["a.jpg"] == "empty"
    assert statuses["b.jpg"] == "needs_review"


# ─── execute_logic validation ─────────────────────────────────────────────────

def test_execute_logic_error_no_service_url(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(tmp_path / "cim_log")
    result = proc.execute_logic({"service_url": "", "dataset_id": "d1"})
    assert result["mode"] == "error"
    assert "Service URL" in result["error"]


def test_execute_logic_error_no_dataset_id(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(tmp_path / "cim_log")
    result = proc.execute_logic({"service_url": "http://svc", "dataset_id": ""})
    assert result["mode"] == "error"
    assert "資料集" in result["error"]


def test_execute_logic_uses_existing_dir(tmp_path, monkeypatch):
    """overwrite=False + existing dir → skip download, scan existing files."""
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    proc = _load(cim_log)

    # Pre-create a "downloads/myds_20240101_000000" dir with one image
    dl_dir = cim_log / "downloads" / "myds_20240101_000000"
    dl_dir.mkdir(parents=True)
    (dl_dir / "img.jpg").write_bytes(b"img")

    result = proc.execute_logic({
        "service_url": "http://svc",
        "dataset_id": "d1",
        "dataset_name": "myds",
        "overwrite": False,
    })
    assert result["mode"] == "done"
    assert result["total"] == 1
    assert result["empty"] == 1


def test_execute_logic_download_failure(tmp_path, monkeypatch):
    """Download network error → mode='error'."""
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))

    # Fake requests that always raises
    fake_req = types.ModuleType("requests")
    def _bad_get(*a, **kw):
        raise RuntimeError("network error")
    fake_req.get = _bad_get
    monkeypatch.setitem(sys.modules, "requests", fake_req)

    proc = _load(cim_log)
    result = proc.execute_logic({
        "service_url": "http://svc",
        "dataset_id": "d1",
        "dataset_name": "newds",
        "overwrite": True,
    })
    assert result["mode"] == "error"
    assert "下載失敗" in result["error"]
