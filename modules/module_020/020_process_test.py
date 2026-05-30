from __future__ import annotations

import importlib.util
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

_HERE = Path(__file__).resolve().parent


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_list_submissions_builds_correct_url(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(_HERE / "020_process.py", "_020_proc_url")

    captured = []

    def mock_get_json(url, timeout=15):
        captured.append(url)
        return {"total": 0, "page": 1, "page_size": 20, "items": []}

    proc._get_json = mock_get_json

    proc.list_submissions({
        "service_url": "http://svc",
        "nt_account": "HCTSAIK",
        "system_name": "iWISC",
        "data_type": "Simulation",
        "date_from": "2026-04-24",
        "date_to": "2026-05-24",
        "page": 1,
        "page_size": 20,
    })

    assert len(captured) == 1
    url = captured[0]
    assert "system_name=iWISC" in url
    assert "data_type=Simulation" in url
    assert "date_from=2026-04-24" in url
    assert "nt_account=HCTSAIK" in url


def test_list_submissions_omits_data_type_when_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(_HERE / "020_process.py", "_020_proc_no_type")

    captured = []

    def mock_get_json(url, timeout=15):
        captured.append(url)
        return {"total": 0, "page": 1, "page_size": 20, "items": []}

    proc._get_json = mock_get_json

    proc.list_submissions({
        "service_url": "http://svc",
        "nt_account": "HCTSAIK",
        "system_name": "SMM",
        "data_type": "",
        "date_from": "2026-04-01",
        "date_to": "2026-05-01",
        "page": 1,
        "page_size": 20,
    })

    url = captured[0]
    assert "data_type" not in url


def test_list_submissions_error_on_missing_service_url(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(_HERE / "020_process.py", "_020_proc_no_url")

    result = proc.list_submissions({"service_url": "", "nt_account": "X", "system_name": ""})
    assert result["mode"] == "error"
    assert result["total"] == 0


def test_list_submissions_omits_nt_account_when_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(_HERE / "020_process.py", "_020_proc_no_nt")

    captured = []

    def mock_get_json(url, timeout=15):
        captured.append(url)
        return {"total": 0, "page": 1, "page_size": 20, "items": []}

    proc._get_json = mock_get_json

    proc.list_submissions({
        "service_url": "http://svc",
        "nt_account": "",
        "system_name": "",
        "data_type": "",
        "date_from": "2026-04-01",
        "date_to": "2026-05-01",
        "page": 1,
        "page_size": 20,
    })

    url = captured[0]
    assert "nt_account" not in url
    assert "system_name" not in url


def test_download_writes_zip_and_extracts(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(_HERE / "020_process.py", "_020_proc_dl")

    # 準備一個假 ZIP
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("images/img001.jpg", b"fake jpg")
        zf.writestr("annotations/img001.json", json.dumps({"shapes": []}))
        zf.writestr("manifest.json", json.dumps({"submit_id": "test-uuid"}))
    zip_bytes = buf.getvalue()

    def mock_stream(url, dest, progress_cb=None, timeout=120):
        dest.write_bytes(zip_bytes)
        return len(zip_bytes)

    proc._download_stream = mock_stream

    result = proc.execute_logic({
        "service_url": "http://svc",
        "nt_account": "HCTSAIK",
        "submit_id": "test-uuid",
    })

    assert result["mode"] == "done"
    assert result["size_bytes"] == len(zip_bytes)
    extract_dir = Path(result["extract_dir"])
    assert (extract_dir / "manifest.json").exists()
    assert (extract_dir / "images" / "img001.jpg").exists()


def test_download_error_on_missing_submit_id(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(_HERE / "020_process.py", "_020_proc_no_sid")

    result = proc.execute_logic({
        "service_url": "http://svc",
        "nt_account": "HCTSAIK",
        "submit_id": "",
    })
    assert result["mode"] == "error"
