from __future__ import annotations

import base64
import importlib.util
import os
import sqlite3
from pathlib import Path

import cv2
import numpy as np
import pytest

_PROCESS_FILE = Path(__file__).parent / "005_process.py"
_spec = importlib.util.spec_from_file_location("module_005_process", _PROCESS_FILE)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
execute_logic = _mod.execute_logic

_TEST_DATE = "2099-01-15"
_TEST_TIMESTAMP = f"{_TEST_DATE} 10:30:00"


def _make_image_bytes() -> bytes:
    arr = np.zeros((100, 120), dtype=np.uint8)
    arr[10:90, 15:105] = 200
    _, buf = cv2.imencode(".png", arr)
    return buf.tobytes()


@pytest.fixture()
def db_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path))
    db = tmp_path / "edge_records.sqlite"
    img_blob = _make_image_bytes()
    with sqlite3.connect(db) as conn:
        conn.execute("""
            CREATE TABLE edge_records (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                parts                 TEXT,
                image_name            TEXT,
                left_roughness        REAL,
                right_roughness       REAL,
                frequency             REAL,
                intensity             REAL,
                image_width           INTEGER,
                image_height          INTEGER,
                timestamp             TEXT,
                image_blob            BLOB,
                gradient_dir_variance REAL,
                psd_energy_ratio      REAL
            )
        """)
        conn.execute(
            """INSERT INTO edge_records
               (parts, image_name, left_roughness, right_roughness,
                frequency, intensity, image_width, image_height, timestamp, image_blob,
                gradient_dir_variance, psd_energy_ratio)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("P-001", "sample.png", 1.5, 2.3, 12.0, 5.0, 120, 100,
             _TEST_TIMESTAMP, img_blob, 0.42, 0.31),
        )
    return tmp_path


def test_returns_required_keys(db_dir):
    r = execute_logic({"date_from": _TEST_DATE, "date_to": _TEST_DATE})
    assert "date_from" in r
    assert "date_to" in r
    assert "records" in r


def test_records_is_list(db_dir):
    r = execute_logic({"date_from": _TEST_DATE, "date_to": _TEST_DATE})
    assert isinstance(r["records"], list)


def test_finds_record_in_range(db_dir):
    r = execute_logic({"date_from": "2099-01-01", "date_to": "2099-01-31"})
    assert len(r["records"]) == 1


def test_exact_date_works(db_dir):
    r = execute_logic({"date_from": _TEST_DATE, "date_to": _TEST_DATE})
    assert len(r["records"]) == 1


def test_empty_result_outside_range(db_dir):
    r = execute_logic({"date_from": "1999-01-01", "date_to": "1999-12-31"})
    assert r["records"] == []


def test_record_fields_present(db_dir):
    rec = execute_logic({"date_from": _TEST_DATE, "date_to": _TEST_DATE})["records"][0]
    for key in ("id", "parts", "image_name", "left_roughness", "right_roughness",
                "frequency", "intensity", "image_width", "image_height", "timestamp",
                "image_b64", "gradient_dir_variance", "psd_energy_ratio",
                "fit_overall", "fit_offset_score", "fit_left", "fit_right", "fit_avg_dist",
                "fit_left_signed_dist", "fit_right_signed_dist"):
        assert key in rec


def test_missing_fit_columns_are_backward_compatible(db_dir):
    rec = execute_logic({"date_from": _TEST_DATE, "date_to": _TEST_DATE})["records"][0]
    assert rec["fit_overall"] is None
    assert rec["fit_offset_score"] is None
    assert rec["fit_avg_dist"] is None


def test_new_metrics_values(db_dir):
    rec = execute_logic({"date_from": _TEST_DATE, "date_to": _TEST_DATE})["records"][0]
    assert rec["gradient_dir_variance"] == pytest.approx(0.42)
    assert rec["psd_energy_ratio"] == pytest.approx(0.31)


def test_image_b64_is_valid(db_dir):
    rec = execute_logic({"date_from": _TEST_DATE, "date_to": _TEST_DATE})["records"][0]
    assert rec["image_b64"] is not None
    raw = base64.b64decode(rec["image_b64"])
    assert len(raw) > 0


def test_no_date_returns_error():
    r = execute_logic({"date_from": "", "date_to": ""})
    assert r.get("error") == "no_date"
    assert r["records"] == []


def test_no_db_returns_error(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path))
    r = execute_logic({"date_from": _TEST_DATE, "date_to": _TEST_DATE})
    assert r.get("error") == "no_db"


def test_date_passthrough(db_dir):
    r = execute_logic({"date_from": _TEST_DATE, "date_to": _TEST_DATE})
    assert r["date_from"] == _TEST_DATE
    assert r["date_to"] == _TEST_DATE


def test_no_streamlit_import():
    src = _PROCESS_FILE.read_text(encoding="utf-8")
    assert "import streamlit" not in src
    assert "from streamlit" not in src
