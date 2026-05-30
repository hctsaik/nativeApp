from __future__ import annotations

"""
module_010/010_process_test.py — pytest 測試套件。

執行方式：
    pytest scripts/module_010/010_process_test.py -v
"""

import importlib.util as _ilu
import json
import sqlite3
from pathlib import Path

import pytest

# ─── 動態載入待測模組 ─────────────────────────────────────────────────────────

_HERE = Path(__file__).resolve().parent


def _load_module(name: str, path: Path):
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_proc = _load_module("_010_process", _HERE / "010_process.py")
_mdb = _load_module("_manifest_db", _HERE.parents[3] / "scripts" / "shared" / "_manifest_db.py")


# ─── 輔助：建立測試用 JPG ──────────────────────────────────────────────────────

def _make_jpg(path: Path, width: int = 64, height: int = 48) -> None:
    """用 PIL 建立最小合法 JPEG 測試圖片。"""
    from PIL import Image

    img = Image.new("RGB", (width, height), color=(128, 64, 32))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path), format="JPEG")


# ─── 測試 scan_folder ─────────────────────────────────────────────────────────

class TestScanFolder:
    def test_empty_folder_returns_empty_list(self, tmp_path: Path):
        """掃描空資料夾應回傳空 list。"""
        items = _proc.scan_folder(str(tmp_path), recursive=True, extensions=[".jpg"])
        assert items == []

    def test_scan_finds_images(self, tmp_path: Path):
        """掃描含圖片的資料夾，應正確回傳 item dict 清單。"""
        img1 = tmp_path / "a.jpg"
        img2 = tmp_path / "b.png"
        _make_jpg(img1)
        _make_jpg(img2, width=32, height=32)

        items = _proc.scan_folder(
            str(tmp_path), recursive=False, extensions=[".jpg", ".png"]
        )
        assert len(items) == 2
        paths = {item["file_path"] for item in items}
        assert str(img1.resolve()) in paths
        assert str(img2.resolve()) in paths
        for item in items:
            assert "item_id" in item
            assert item["width"] is not None
            assert item["height"] is not None
            assert item["file_hash"] is not None

    def test_recursive_vs_non_recursive(self, tmp_path: Path):
        """遞迴掃描應找到子資料夾圖片；非遞迴則不找。"""
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_jpg(tmp_path / "root.jpg")
        _make_jpg(sub / "child.jpg")

        non_recursive = _proc.scan_folder(str(tmp_path), recursive=False, extensions=[".jpg"])
        recursive = _proc.scan_folder(str(tmp_path), recursive=True, extensions=[".jpg"])

        assert len(non_recursive) == 1
        assert len(recursive) == 2

    def test_extension_filter(self, tmp_path: Path):
        """只有符合副檔名的圖片才應被納入。"""
        _make_jpg(tmp_path / "img.jpg")
        _make_jpg(tmp_path / "img.png")
        (tmp_path / "doc.txt").write_text("hello", encoding="utf-8")

        items_jpg = _proc.scan_folder(str(tmp_path), recursive=False, extensions=[".jpg"])
        items_all = _proc.scan_folder(
            str(tmp_path), recursive=False, extensions=[".jpg", ".png"]
        )

        assert len(items_jpg) == 1
        assert items_jpg[0]["file_path"].endswith(".jpg")
        assert len(items_all) == 2


# ─── 測試 execute_logic ───────────────────────────────────────────────────────

class TestExecuteLogic:
    def test_folder_mode_success(self, tmp_path: Path, monkeypatch):
        """execute_logic folder mode 應成功建立 Manifest 並回傳 ready。"""
        img = tmp_path / "test.jpg"
        _make_jpg(img)

        # 指定 db 到 tmp_path
        db_path = tmp_path / "db" / "manifest.sqlite"
        monkeypatch.setattr(_proc._cfg, "get_manifest_db_path", lambda: db_path)

        result = _proc.execute_logic(
            {
                "source_type": "folder",
                "manifest_name": "測試資料集",
                "folder_path": str(tmp_path),
                "recursive": False,
                "extensions": [".jpg"],
            }
        )

        assert result["mode"] == "ready"
        assert result["manifest_name"] == "測試資料集"
        assert result["source_type"] == "folder"
        assert result["total_count"] == 1
        assert len(result["items"]) == 1
        assert result["error"] is None
        assert result["manifest_id"] != ""

    def test_folder_path_not_exist_returns_error(self, tmp_path: Path, monkeypatch):
        """資料夾路徑不存在時，execute_logic 應回傳 mode='error'。"""
        db_path = tmp_path / "db" / "manifest.sqlite"
        monkeypatch.setattr(_proc._cfg, "get_manifest_db_path", lambda: db_path)

        result = _proc.execute_logic(
            {
                "source_type": "folder",
                "manifest_name": "不存在的路徑",
                "folder_path": str(tmp_path / "no_such_dir"),
                "recursive": False,
                "extensions": [".jpg"],
            }
        )

        assert result["mode"] == "error"
        assert result["error"] is not None
        assert "不存在" in result["error"] or "not exist" in result["error"].lower()

    def test_empty_folder_path_returns_error(self, tmp_path: Path, monkeypatch):
        """空路徑應回傳 mode='error' 並含提示訊息。"""
        db_path = tmp_path / "db" / "manifest.sqlite"
        monkeypatch.setattr(_proc._cfg, "get_manifest_db_path", lambda: db_path)

        result = _proc.execute_logic(
            {
                "source_type": "folder",
                "manifest_name": "無路徑測試",
                "folder_path": "",
                "recursive": False,
                "extensions": [".jpg"],
            }
        )

        assert result["mode"] == "error"


# ─── 測試 _manifest_db ────────────────────────────────────────────────────────

class TestManifestDb:
    def test_create_and_get_manifest(self, tmp_path: Path):
        """create_manifest 後 get_manifest 應能取回相同記錄。"""
        db = tmp_path / "test.sqlite"
        _mdb.init_db(db)

        mid = "manifest_abc123"
        record = _mdb.create_manifest(db, mid, "我的資料集", "folder", {"path": "/tmp"})

        assert record is not None
        assert record["manifest_id"] == mid
        assert record["name"] == "我的資料集"
        assert record["source_type"] == "folder"
        assert record["status"] == "draft"

        fetched = _mdb.get_manifest(db, mid)
        assert fetched is not None
        assert fetched["manifest_id"] == mid

    def test_add_items_and_get_items(self, tmp_path: Path):
        """add_manifest_items 後 get_manifest_items 應回傳相同筆數。"""
        db = tmp_path / "test.sqlite"
        _mdb.init_db(db)

        mid = "manifest_xyz"
        _mdb.create_manifest(db, mid, "圖片集", "folder", {})

        items = [
            {"item_id": f"item_{i}", "file_path": f"/images/{i}.jpg", "width": 640, "height": 480}
            for i in range(5)
        ]
        count = _mdb.add_manifest_items(db, mid, items)
        assert count == 5

        fetched_items = _mdb.get_manifest_items(db, mid)
        assert len(fetched_items) == 5
        fetched_ids = {it["item_id"] for it in fetched_items}
        assert fetched_ids == {f"item_{i}" for i in range(5)}

    def test_list_manifests_order(self, tmp_path: Path):
        """list_manifests 應依 created_at 倒序排列。"""
        db = tmp_path / "test.sqlite"
        _mdb.init_db(db)

        _mdb.create_manifest(db, "m_first", "第一個", "folder", {})
        _mdb.create_manifest(db, "m_second", "第二個", "folder", {})

        manifests = _mdb.list_manifests(db)
        assert len(manifests) == 2
        # 倒序：最新建立的排在前面
        assert manifests[0]["manifest_id"] == "m_second"
        assert manifests[1]["manifest_id"] == "m_first"

    def test_delete_manifest_cascades(self, tmp_path: Path):
        """刪除 manifest 後，items 也應一起被刪除（CASCADE）。"""
        db = tmp_path / "test.sqlite"
        _mdb.init_db(db)

        mid = "m_to_delete"
        _mdb.create_manifest(db, mid, "待刪資料集", "folder", {})
        _mdb.add_manifest_items(db, mid, [{"item_id": "i1", "file_path": "/a.jpg"}])

        _mdb.delete_manifest(db, mid)

        assert _mdb.get_manifest(db, mid) is None
        items = _mdb.get_manifest_items(db, mid)
        assert items == []

    def test_upsert_annotation_result(self, tmp_path: Path):
        """upsert_annotation_result 應可以新增並更新同 run_id+item_id 的記錄。"""
        db = tmp_path / "test.sqlite"
        _mdb.init_db(db)

        mid = "m_ann"
        _mdb.create_manifest(db, mid, "標注資料集", "folder", {})

        _mdb.upsert_annotation_result(
            db, "run_001", mid, "item_a",
            '{"label": "cat"}', "cat", 0.95, "model"
        )
        results = _mdb.get_annotation_results(db, "run_001")
        assert len(results) == 1
        assert results[0]["label"] == "cat"
        assert results[0]["confidence"] == pytest.approx(0.95)

        # 更新
        _mdb.upsert_annotation_result(
            db, "run_001", mid, "item_a",
            '{"label": "dog"}', "dog", 0.88, "manual"
        )
        results_updated = _mdb.get_annotation_results(db, "run_001")
        assert len(results_updated) == 1
        assert results_updated[0]["label"] == "dog"

    def test_create_and_get_export(self, tmp_path: Path):
        """create_export_record 後 get_exports 應能取回記錄。"""
        db = tmp_path / "test.sqlite"
        _mdb.init_db(db)

        mid = "m_exp"
        _mdb.create_manifest(db, mid, "匯出測試", "folder", {})
        _mdb.create_export_record(db, "run_exp", mid, "coco_json", "/out/coco.json", 42)

        exports = _mdb.get_exports(db, mid)
        assert len(exports) == 1
        assert exports[0]["export_format"] == "coco_json"
        assert exports[0]["item_count"] == 42

    def test_get_manifest_items_with_limit(self, tmp_path: Path):
        """get_manifest_items limit 參數應正確限制回傳筆數。"""
        db = tmp_path / "test.sqlite"
        _mdb.init_db(db)

        mid = "m_limit"
        _mdb.create_manifest(db, mid, "限制測試", "folder", {})
        items = [{"item_id": f"i{n}", "file_path": f"/img/{n}.jpg"} for n in range(10)]
        _mdb.add_manifest_items(db, mid, items)

        limited = _mdb.get_manifest_items(db, mid, limit=3)
        assert len(limited) == 3

        all_items = _mdb.get_manifest_items(db, mid)
        assert len(all_items) == 10
