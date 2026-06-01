"""工具分發來源抽象（規格 §5.2）。

``ToolDistributionSource`` 切出「從哪裡取得已核准工具版本」的邊界：
今天用 :class:`LocalFsSource`（本機資料夾），未來換 :class:`HttpRegistrySource`
（內網 registry-server）只是改類別 + base URL，不動商業邏輯。

兩個 source 的 :meth:`fetch` 取回 artifact 後都**必須驗章**（:func:`verify_artifact`），
驗章失敗丟 :class:`ValueError` —— 拒絕安裝未驗證 / 被竄改的碼。

HTTP 用 stdlib :mod:`urllib.request`（engine.py 已用此），不引入 requests/httpx
當執行期相依。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import asdict
from pathlib import Path

from core.distribution.signing import (
    ToolArtifact,
    ToolArtifactMeta,
    get_secret,
    meta_of,
    verify_artifact,
)


# ---------------------------------------------------------------------------
# 序列化 helper（artifact ↔ dict）
# ---------------------------------------------------------------------------


def artifact_to_dict(artifact: ToolArtifact) -> dict:
    """ToolArtifact → 純 dict（可直接 ``json.dumps``）。"""
    return asdict(artifact)


def artifact_from_dict(data: dict) -> ToolArtifact:
    """dict → ToolArtifact（只取已知欄位，忽略多餘鍵以利前後相容）。"""
    return ToolArtifact(
        tool_id=data["tool_id"],
        version=data["version"],
        channel=data["channel"],
        content=data["content"],
        sha256=data["sha256"],
        signature=data["signature"],
        created_at=data["created_at"],
        author=data["author"],
    )


def meta_to_dict(meta: ToolArtifactMeta) -> dict:
    """ToolArtifactMeta → 純 dict。"""
    return asdict(meta)


def meta_from_dict(data: dict) -> ToolArtifactMeta:
    """dict → ToolArtifactMeta。"""
    return ToolArtifactMeta(
        tool_id=data["tool_id"],
        version=data["version"],
        channel=data["channel"],
        sha256=data["sha256"],
        created_at=data["created_at"],
    )


# ---------------------------------------------------------------------------
# Source 抽象
# ---------------------------------------------------------------------------


class ToolDistributionSource(ABC):
    """工具分發來源介面。"""

    @abstractmethod
    def list_artifacts(self, channel: str) -> list[ToolArtifactMeta]:
        """列出某 channel 的所有 artifact 目錄（輕量，不含 content）。"""
        raise NotImplementedError

    @abstractmethod
    def fetch(self, tool_id: str, version: str) -> ToolArtifact:
        """取得完整 artifact；取回後必須驗章，失敗丟 ValueError。"""
        raise NotImplementedError


class LocalFsSource(ToolDistributionSource):
    """讀本機資料夾的分發來源。

    版面：``<root>/<channel>/<tool_id>/<version>.json``（artifact 序列化為 JSON）。
    這是今天就能用的 source，也是測試與 start-fleet 模擬的預設。
    """

    def __init__(self, root: str | Path, secret: str | None = None) -> None:
        self._root = Path(root)
        self._secret = secret if secret is not None else get_secret()

    # -- 路徑 helper --------------------------------------------------------

    def _channel_dir(self, channel: str) -> Path:
        return self._root / channel

    def _artifact_path(self, channel: str, tool_id: str, version: str) -> Path:
        return self._channel_dir(channel) / tool_id / f"{version}.json"

    # -- 寫入（測試 / publish 模擬用） --------------------------------------

    def save(self, artifact: ToolArtifact) -> Path:
        """把 artifact 寫進 ``<root>/<channel>/<tool_id>/<version>.json``。

        同 (channel, tool_id, version) 覆寫。回傳寫入路徑。
        """
        path = self._artifact_path(artifact.channel, artifact.tool_id, artifact.version)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(artifact_to_dict(artifact), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    # -- ToolDistributionSource --------------------------------------------

    def list_artifacts(self, channel: str) -> list[ToolArtifactMeta]:
        channel_dir = self._channel_dir(channel)
        if not channel_dir.is_dir():
            return []
        metas: list[ToolArtifactMeta] = []
        for tool_dir in sorted(channel_dir.iterdir()):
            if not tool_dir.is_dir():
                continue
            for version_file in sorted(tool_dir.glob("*.json")):
                try:
                    data = json.loads(version_file.read_text(encoding="utf-8"))
                    metas.append(meta_of(artifact_from_dict(data)))
                except (json.JSONDecodeError, KeyError, OSError):
                    # 壞檔不應讓整個目錄列舉失敗
                    continue
        return metas

    def fetch(self, tool_id: str, version: str) -> ToolArtifact:
        # artifact 可能落在任一 channel 子目錄；逐一尋找
        for channel_dir in sorted(p for p in self._root.iterdir() if p.is_dir()) if self._root.is_dir() else []:
            path = channel_dir / tool_id / f"{version}.json"
            if path.exists():
                artifact = artifact_from_dict(json.loads(path.read_text(encoding="utf-8")))
                if not verify_artifact(artifact, self._secret):
                    raise ValueError(
                        f"Artifact signature/hash verification failed: {tool_id}@{version}"
                    )
                return artifact
        raise FileNotFoundError(f"Artifact not found: {tool_id}@{version}")


class HttpRegistrySource(ToolDistributionSource):
    """打 registry-server HTTP 的分發來源（stdlib urllib）。

    端點：``GET {base}/catalog?channel=``、``GET {base}/artifact/{tool_id}/{version}``。
    與 :class:`LocalFsSource` 同介面 → dev→prod 只換這個類別 + base URL。
    """

    def __init__(self, base_url: str, secret: str | None = None, timeout: float = 10.0) -> None:
        self._base = base_url.rstrip("/")
        self._secret = secret if secret is not None else get_secret()
        self._timeout = timeout

    def _get_json(self, path: str) -> object:
        url = f"{self._base}{path}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def list_artifacts(self, channel: str) -> list[ToolArtifactMeta]:
        query = urllib.parse.urlencode({"channel": channel})
        data = self._get_json(f"/catalog?{query}")
        return [meta_from_dict(item) for item in data]

    def fetch(self, tool_id: str, version: str) -> ToolArtifact:
        enc_id = urllib.parse.quote(tool_id, safe="")
        enc_ver = urllib.parse.quote(version, safe="")
        try:
            data = self._get_json(f"/artifact/{enc_id}/{enc_ver}")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise FileNotFoundError(f"Artifact not found: {tool_id}@{version}") from exc
            raise
        artifact = artifact_from_dict(data)
        if not verify_artifact(artifact, self._secret):
            raise ValueError(
                f"Artifact signature/hash verification failed: {tool_id}@{version}"
            )
        return artifact
