from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from core.distribution import (
    HttpRegistrySource,
    LocalFsSource,
    ToolArtifact,
    ToolArtifactMeta,
    artifact_from_dict,
    artifact_to_dict,
    content_sha256,
    make_artifact,
    meta_of,
    sign,
    verify,
    verify_artifact,
)

SECRET = "unit-test-secret"

SAMPLE_CONTENT = {
    "plugin.yaml": "id: module_042\nname: Demo\nversion: 1.0.0\n",
    "042_process.py": "def execute_logic(params):\n    return {'ok': True}\n",
}


# ---------------------------------------------------------------------------
# Canonical hash
# ---------------------------------------------------------------------------


def test_content_sha256_is_key_order_independent() -> None:
    a = {"b": 2, "a": 1, "c": {"y": 9, "x": 8}}
    b = {"a": 1, "c": {"x": 8, "y": 9}, "b": 2}
    assert content_sha256(a) == content_sha256(b)


def test_content_sha256_changes_when_content_changes() -> None:
    base = content_sha256(SAMPLE_CONTENT)
    mutated = dict(SAMPLE_CONTENT)
    mutated["042_process.py"] += "# tampered\n"
    assert content_sha256(mutated) != base


def test_content_sha256_preserves_non_ascii() -> None:
    # ensure_ascii=False — 非 ASCII 內容仍可重算且穩定
    content = {"note": "影像標註工具"}
    assert content_sha256(content) == content_sha256({"note": "影像標註工具"})


# ---------------------------------------------------------------------------
# sign / verify
# ---------------------------------------------------------------------------


def test_sign_then_verify_roundtrip() -> None:
    sha = content_sha256(SAMPLE_CONTENT)
    signature = sign(sha, SECRET)
    assert verify(sha, signature, SECRET) is True


def test_verify_fails_with_wrong_secret() -> None:
    sha = content_sha256(SAMPLE_CONTENT)
    signature = sign(sha, SECRET)
    assert verify(sha, signature, "other-secret") is False


# ---------------------------------------------------------------------------
# make_artifact / verify_artifact
# ---------------------------------------------------------------------------


def test_make_artifact_produces_verifiable_artifact() -> None:
    artifact = make_artifact(
        "module_042", "1.0.0", "prod", SAMPLE_CONTENT, "tester", SECRET
    )
    assert isinstance(artifact, ToolArtifact)
    assert artifact.tool_id == "module_042"
    assert artifact.sha256 == content_sha256(SAMPLE_CONTENT)
    assert artifact.created_at  # ISO timestamp present
    assert verify_artifact(artifact, SECRET) is True


def test_verify_artifact_false_when_content_tampered() -> None:
    artifact = make_artifact(
        "module_042", "1.0.0", "prod", SAMPLE_CONTENT, "tester", SECRET
    )
    tampered_content = dict(artifact.content)
    tampered_content["042_process.py"] = "import os  # injected\n"
    tampered = replace(artifact, content=tampered_content)
    # sha256/signature 仍是舊的 → content 與 sha256 不符
    assert verify_artifact(tampered, SECRET) is False


def test_verify_artifact_false_when_signature_tampered() -> None:
    artifact = make_artifact(
        "module_042", "1.0.0", "prod", SAMPLE_CONTENT, "tester", SECRET
    )
    tampered = replace(artifact, signature="deadbeef")
    assert verify_artifact(tampered, SECRET) is False


def test_verify_artifact_false_when_sha_tampered() -> None:
    artifact = make_artifact(
        "module_042", "1.0.0", "prod", SAMPLE_CONTENT, "tester", SECRET
    )
    tampered = replace(artifact, sha256="0" * 64)
    assert verify_artifact(tampered, SECRET) is False


# ---------------------------------------------------------------------------
# 序列化 helper
# ---------------------------------------------------------------------------


def test_artifact_dict_roundtrip() -> None:
    artifact = make_artifact(
        "module_042", "1.0.0", "prod", SAMPLE_CONTENT, "tester", SECRET
    )
    restored = artifact_from_dict(artifact_to_dict(artifact))
    assert restored == artifact


def test_meta_of_drops_content() -> None:
    artifact = make_artifact(
        "module_042", "2.1.0", "dev", SAMPLE_CONTENT, "tester", SECRET
    )
    meta = meta_of(artifact)
    assert isinstance(meta, ToolArtifactMeta)
    assert meta.tool_id == "module_042"
    assert meta.version == "2.1.0"
    assert meta.channel == "dev"
    assert meta.sha256 == artifact.sha256
    assert not hasattr(meta, "content")


# ---------------------------------------------------------------------------
# LocalFsSource
# ---------------------------------------------------------------------------


def test_local_fs_source_save_list_fetch_roundtrip(tmp_path: Path) -> None:
    source = LocalFsSource(tmp_path, secret=SECRET)
    artifact = make_artifact(
        "module_042", "1.0.0", "prod", SAMPLE_CONTENT, "tester", SECRET
    )
    path = source.save(artifact)
    assert path.exists()
    assert path == tmp_path / "prod" / "module_042" / "1.0.0.json"

    metas = source.list_artifacts("prod")
    assert len(metas) == 1
    assert metas[0].tool_id == "module_042"
    assert metas[0].version == "1.0.0"

    fetched = source.fetch("module_042", "1.0.0")
    assert fetched == artifact


def test_local_fs_source_list_empty_channel(tmp_path: Path) -> None:
    source = LocalFsSource(tmp_path, secret=SECRET)
    assert source.list_artifacts("prod") == []


def test_local_fs_source_fetch_missing_raises(tmp_path: Path) -> None:
    source = LocalFsSource(tmp_path, secret=SECRET)
    with pytest.raises(FileNotFoundError):
        source.fetch("module_999", "9.9.9")


def test_local_fs_source_fetch_rejects_tampered_artifact(tmp_path: Path) -> None:
    source = LocalFsSource(tmp_path, secret=SECRET)
    artifact = make_artifact(
        "module_042", "1.0.0", "prod", SAMPLE_CONTENT, "tester", SECRET
    )
    path = source.save(artifact)
    # 直接竄改磁碟上的 JSON content（但不更新 sha256/signature）
    data = json.loads(path.read_text(encoding="utf-8"))
    data["content"]["042_process.py"] = "import os  # injected\n"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError):
        source.fetch("module_042", "1.0.0")


def test_local_fs_source_fetch_rejects_wrong_secret(tmp_path: Path) -> None:
    # 用 SECRET 簽，但 source 用別的密鑰驗 → 拒裝
    LocalFsSource(tmp_path, secret=SECRET).save(
        make_artifact("module_042", "1.0.0", "prod", SAMPLE_CONTENT, "tester", SECRET)
    )
    bad_source = LocalFsSource(tmp_path, secret="different-secret")
    with pytest.raises(ValueError):
        bad_source.fetch("module_042", "1.0.0")


# ---------------------------------------------------------------------------
# HttpRegistrySource（透過 TestClient base 取回；端到端在 test_registry_server）
# ---------------------------------------------------------------------------


def test_http_source_constructs_with_base_url() -> None:
    src = HttpRegistrySource("http://127.0.0.1:9000/", secret=SECRET)
    # 尾端斜線應被去除，避免雙斜線
    assert src._base == "http://127.0.0.1:9000"
