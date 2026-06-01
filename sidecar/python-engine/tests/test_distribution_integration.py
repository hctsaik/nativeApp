"""整合測試（功能 #1）：engine 的分發拉取 helper 端到端行為。

證明：從一個 LocalFsSource 拉取已簽章 artifact → 驗章 → 寫進本機 catalog →
可從 catalog 讀回；且被竄改的 artifact 會被拒裝（驗章失敗 → 不發布）。
"""

from __future__ import annotations

import json
from pathlib import Path

import engine
from core.distribution import LocalFsSource, get_secret, make_artifact
from management_schema import SQLiteManagementSchema
from management_store import SQLiteManagementStore


def _fresh_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "tools.sqlite"
    SQLiteManagementSchema(db_path).ensure_current()
    return db_path


def _sample_content(tool_id: str = "module_900", version: str = "1.0.0") -> dict[str, str]:
    return {
        "plugin.yaml": (
            f"id: {tool_id}\nname: 分發測試工具\nversion: {version}\n"
            "runner: cv_framework\ncategory: module\nenabled: true\n"
        ),
        "900_process.py": "def execute_logic(params):\n    return {'mode': 'ready'}\n",
    }


def test_pull_publishes_verified_artifact(tmp_path):
    db_path = _fresh_db(tmp_path)
    secret = get_secret()
    src_root = tmp_path / "registry"
    source = LocalFsSource(src_root, secret=secret)
    content = _sample_content()
    source.save(make_artifact("module_900", "1.0.0", "prod", content, "tester", secret))

    report = engine.pull_distribution_into_catalog(db_path, f"local:{src_root}")

    assert report["pulled"] == ["module_900@1.0.0"]
    assert report["skipped"] == []
    # snapshot 應可從本機 catalog 讀回，且內容與來源一致
    stored = SQLiteManagementStore(db_path).get_active_snapshot_content("module_900")
    assert stored == content


def test_pull_skips_tampered_artifact(tmp_path):
    db_path = _fresh_db(tmp_path)
    secret = get_secret()
    src_root = tmp_path / "registry"
    source = LocalFsSource(src_root, secret=secret)
    content = _sample_content("module_901")
    path = source.save(make_artifact("module_901", "1.0.0", "prod", content, "tester", secret))

    # 竄改 content 但保留舊 sha/signature → 驗章必失敗
    data = json.loads(path.read_text(encoding="utf-8"))
    data["content"]["900_process.py"] = "def execute_logic(params):\n    return {'evil': True}\n"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    report = engine.pull_distribution_into_catalog(db_path, f"local:{src_root}")

    assert report["pulled"] == []
    assert report["skipped"] == ["module_901@1.0.0"]
    # 拒裝 → catalog 不應出現此工具
    assert SQLiteManagementStore(db_path).get_active_snapshot_content("module_901") is None


def test_pull_with_missing_source_is_safe(tmp_path):
    db_path = _fresh_db(tmp_path)
    # 不存在的來源目錄 → 安全回空報告，不可拋例外（不可中斷 engine 啟動）
    report = engine.pull_distribution_into_catalog(db_path, f"local:{tmp_path / 'does-not-exist'}")
    assert report["pulled"] == []
    assert report["skipped"] == []
