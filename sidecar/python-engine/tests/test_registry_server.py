from __future__ import annotations

import urllib.error
import urllib.parse
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.distribution import (
    HttpRegistrySource,
    artifact_to_dict,
    make_artifact,
)
from tools.registry_server import (
    FileArtifactStore,
    SqliteArtifactStore,
    create_app,
)

SECRET = "registry-test-secret"

SAMPLE_CONTENT = {
    "plugin.yaml": "id: module_042\nname: Demo\nversion: 1.0.0\n",
    "042_process.py": "def execute_logic(params):\n    return {'ok': True}\n",
}


def _artifact(tool_id: str = "module_042", version: str = "1.0.0", channel: str = "prod"):
    return make_artifact(tool_id, version, channel, SAMPLE_CONTENT, "tester", SECRET)


@pytest.fixture(params=["file", "sqlite"])
def store(request: pytest.FixtureRequest, tmp_path: Path):
    """同一組測試跑 FileArtifactStore 與 SqliteArtifactStore 兩種後端（DAL 可替換）。"""
    if request.param == "file":
        return FileArtifactStore(tmp_path / "store")
    return SqliteArtifactStore(tmp_path / "store.sqlite")


@pytest.fixture
def client(store) -> TestClient:
    app = create_app(store, secret=SECRET)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------


def test_health_returns_ok(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# publish
# ---------------------------------------------------------------------------


def test_publish_valid_artifact_succeeds(client: TestClient) -> None:
    resp = client.post("/publish", json=artifact_to_dict(_artifact()))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["tool_id"] == "module_042"
    assert body["version"] == "1.0.0"
    assert body["channel"] == "prod"


def test_publish_rejects_tampered_artifact_with_400(client: TestClient) -> None:
    payload = artifact_to_dict(_artifact())
    payload["content"]["042_process.py"] = "import os  # injected\n"  # 不更新 sha256
    resp = client.post("/publish", json=payload)
    assert resp.status_code == 400


def test_publish_rejects_bad_signature_with_400(client: TestClient) -> None:
    payload = artifact_to_dict(_artifact())
    payload["signature"] = "deadbeef"
    resp = client.post("/publish", json=payload)
    assert resp.status_code == 400


def test_publish_rejects_malformed_artifact_with_400(client: TestClient) -> None:
    resp = client.post("/publish", json={"tool_id": "module_042"})  # 缺欄位
    assert resp.status_code == 400


def test_publish_overwrites_same_key(client: TestClient) -> None:
    assert client.post("/publish", json=artifact_to_dict(_artifact())).status_code == 200
    assert client.post("/publish", json=artifact_to_dict(_artifact())).status_code == 200
    catalog = client.get("/catalog", params={"channel": "prod"}).json()
    assert len(catalog) == 1


# ---------------------------------------------------------------------------
# catalog
# ---------------------------------------------------------------------------


def test_catalog_lists_published_metas(client: TestClient) -> None:
    client.post("/publish", json=artifact_to_dict(_artifact("module_042", "1.0.0")))
    client.post("/publish", json=artifact_to_dict(_artifact("module_043", "2.0.0")))

    catalog = client.get("/catalog", params={"channel": "prod"}).json()
    ids = {(m["tool_id"], m["version"]) for m in catalog}
    assert ("module_042", "1.0.0") in ids
    assert ("module_043", "2.0.0") in ids
    # meta 不含 content
    for m in catalog:
        assert "content" not in m
        assert "sha256" in m


def test_catalog_filters_by_channel(client: TestClient) -> None:
    client.post("/publish", json=artifact_to_dict(_artifact(channel="prod")))
    client.post("/publish", json=artifact_to_dict(_artifact(channel="dev")))

    prod = client.get("/catalog", params={"channel": "prod"}).json()
    dev = client.get("/catalog", params={"channel": "dev"}).json()
    assert all(m["channel"] == "prod" for m in prod)
    assert all(m["channel"] == "dev" for m in dev)


def test_catalog_empty_for_unknown_channel(client: TestClient) -> None:
    assert client.get("/catalog", params={"channel": "nope"}).json() == []


# ---------------------------------------------------------------------------
# artifact
# ---------------------------------------------------------------------------


def test_get_artifact_returns_full_payload(client: TestClient) -> None:
    client.post("/publish", json=artifact_to_dict(_artifact()))
    resp = client.get("/artifact/module_042/1.0.0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == SAMPLE_CONTENT
    assert body["tool_id"] == "module_042"


def test_get_artifact_unknown_returns_404(client: TestClient) -> None:
    resp = client.get("/artifact/module_999/9.9.9")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 端到端：HttpRegistrySource 指向 TestClient base → 拉回並驗章通過
# ---------------------------------------------------------------------------


class _TestClientSource(HttpRegistrySource):
    """把 HttpRegistrySource 的 GET 改走 TestClient（測試用，不開實際 socket）。"""

    def __init__(self, test_client: TestClient, secret: str) -> None:
        super().__init__("http://testserver", secret=secret)
        self._tc = test_client

    def _get_json(self, path: str):
        # urllib path 已含 query string；拆給 TestClient
        parsed = urllib.parse.urlsplit(path)
        params = dict(urllib.parse.parse_qsl(parsed.query))
        resp = self._tc.get(parsed.path, params=params)
        if resp.status_code == 404:
            raise urllib.error.HTTPError(path, 404, "Not Found", hdrs=None, fp=None)
        resp.raise_for_status()
        return resp.json()


def test_http_source_against_registry_roundtrip(client: TestClient) -> None:
    client.post("/publish", json=artifact_to_dict(_artifact()))
    source = _TestClientSource(client, SECRET)

    metas = source.list_artifacts("prod")
    assert any(m.tool_id == "module_042" and m.version == "1.0.0" for m in metas)

    fetched = source.fetch("module_042", "1.0.0")  # 內含 verify_artifact
    assert fetched.content == SAMPLE_CONTENT
    assert fetched.tool_id == "module_042"


def test_http_source_fetch_missing_raises_filenotfound(client: TestClient) -> None:
    source = _TestClientSource(client, SECRET)
    with pytest.raises(FileNotFoundError):
        source.fetch("module_999", "9.9.9")
