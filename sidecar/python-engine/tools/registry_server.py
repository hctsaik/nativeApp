"""最小 registry-server（規格 §5.3）—— 可獨立啟動的 FastAPI 分發 registry。

端點：
- ``POST /publish``     收 ToolArtifact JSON，驗章後存進 store（同 key 覆寫）；驗章失敗 → 400。
- ``GET  /catalog?channel=``  回 ``list[ToolArtifactMeta]``。
- ``GET  /artifact/{tool_id}/{version}``  回完整 ToolArtifact；不存在 → 404。
- ``GET  /health``      ``{"status": "ok"}``。

Store 走 DAL 邊界（:class:`ArtifactStore` ABC），本期提供檔案版
（:class:`FileArtifactStore`）與 SQLite 版（:class:`SqliteArtifactStore`）；
日後換 Postgres 只需實作同介面（規格 §2 / §8）。

啟動：``python tools/registry_server.py --port 9000 --store <dir>``，只聽 127.0.0.1。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException

# 允許「python tools/registry_server.py」直接執行：把 python-engine 根目錄加入 path。
import sys as _sys

_ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(_ENGINE_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ENGINE_ROOT))

from core.distribution import (  # noqa: E402
    ToolArtifact,
    ToolArtifactMeta,
    artifact_from_dict,
    artifact_to_dict,
    get_secret,
    meta_of,
    meta_to_dict,
    verify_artifact,
)


# ---------------------------------------------------------------------------
# Store DAL（可替換：FileArtifactStore / SqliteArtifactStore / 日後 Postgres）
# ---------------------------------------------------------------------------


class ArtifactStore(ABC):
    """server 端 artifact 儲存抽象。"""

    @abstractmethod
    def put(self, artifact: ToolArtifact) -> None:
        """存一個 artifact；同 (channel, tool_id, version) 覆寫。"""
        raise NotImplementedError

    @abstractmethod
    def catalog(self, channel: str) -> list[ToolArtifactMeta]:
        """列出某 channel 的目錄（輕量 meta）。"""
        raise NotImplementedError

    @abstractmethod
    def get(self, tool_id: str, version: str) -> ToolArtifact | None:
        """取完整 artifact；不存在回 None。"""
        raise NotImplementedError


class FileArtifactStore(ArtifactStore):
    """以資料夾為後端：``<root>/<channel>/<tool_id>/<version>.json``。"""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, channel: str, tool_id: str, version: str) -> Path:
        return self._root / channel / tool_id / f"{version}.json"

    def put(self, artifact: ToolArtifact) -> None:
        path = self._path(artifact.channel, artifact.tool_id, artifact.version)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(artifact_to_dict(artifact), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def catalog(self, channel: str) -> list[ToolArtifactMeta]:
        channel_dir = self._root / channel
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
                    continue
        return metas

    def get(self, tool_id: str, version: str) -> ToolArtifact | None:
        if not self._root.is_dir():
            return None
        for channel_dir in sorted(p for p in self._root.iterdir() if p.is_dir()):
            path = channel_dir / tool_id / f"{version}.json"
            if path.exists():
                return artifact_from_dict(json.loads(path.read_text(encoding="utf-8")))
        return None


class SqliteArtifactStore(ArtifactStore):
    """以 SQLite 為後端（規格 §2 預留可換 Postgres 的 DAL 形狀）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    tool_id    TEXT NOT NULL,
                    version    TEXT NOT NULL,
                    channel    TEXT NOT NULL,
                    sha256     TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    artifact_json TEXT NOT NULL,
                    PRIMARY KEY (channel, tool_id, version)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def put(self, artifact: ToolArtifact) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO artifacts
                    (tool_id, version, channel, sha256, created_at, artifact_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(channel, tool_id, version) DO UPDATE SET
                    sha256 = excluded.sha256,
                    created_at = excluded.created_at,
                    artifact_json = excluded.artifact_json
                """,
                (
                    artifact.tool_id,
                    artifact.version,
                    artifact.channel,
                    artifact.sha256,
                    artifact.created_at,
                    json.dumps(artifact_to_dict(artifact), ensure_ascii=False),
                ),
            )

    def catalog(self, channel: str) -> list[ToolArtifactMeta]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT tool_id, version, channel, sha256, created_at "
                "FROM artifacts WHERE channel = ? ORDER BY tool_id, version",
                (channel,),
            ).fetchall()
        return [
            ToolArtifactMeta(
                tool_id=r["tool_id"],
                version=r["version"],
                channel=r["channel"],
                sha256=r["sha256"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def get(self, tool_id: str, version: str) -> ToolArtifact | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT artifact_json FROM artifacts WHERE tool_id = ? AND version = ? "
                "ORDER BY channel LIMIT 1",
                (tool_id, version),
            ).fetchone()
        if row is None:
            return None
        return artifact_from_dict(json.loads(row["artifact_json"]))


# ---------------------------------------------------------------------------
# FastAPI app 工廠
# ---------------------------------------------------------------------------


def create_app(store: ArtifactStore, secret: str | None = None) -> FastAPI:
    """建立 registry-server FastAPI app。

    :param store: 可替換的 :class:`ArtifactStore`（測試可注入 tmp store）。
    :param secret: 驗章密鑰；預設讀 ``CIM_DISTRIBUTION_SECRET``。
    """
    app = FastAPI(title="CIM Tool Registry", version="0.1.0")
    sign_secret = secret if secret is not None else get_secret()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/publish")
    def publish(body: dict = Body(...)) -> dict:
        try:
            artifact = artifact_from_dict(body)
        except (KeyError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=f"Malformed artifact: {exc}") from exc
        if not verify_artifact(artifact, sign_secret):
            raise HTTPException(
                status_code=400,
                detail="Artifact signature/hash verification failed",
            )
        store.put(artifact)
        return {
            "status": "ok",
            "tool_id": artifact.tool_id,
            "version": artifact.version,
            "channel": artifact.channel,
        }

    @app.get("/catalog")
    def catalog(channel: str = "prod") -> list[dict]:
        return [meta_to_dict(m) for m in store.catalog(channel)]

    @app.get("/artifact/{tool_id}/{version}")
    def get_artifact(tool_id: str, version: str) -> dict:
        artifact = store.get(tool_id, version)
        if artifact is None:
            raise HTTPException(status_code=404, detail=f"Artifact not found: {tool_id}@{version}")
        return artifact_to_dict(artifact)

    return app


# ---------------------------------------------------------------------------
# CLI 啟動（只聽 127.0.0.1）
# ---------------------------------------------------------------------------


def _build_store(store_arg: str) -> ArtifactStore:
    """依 --store 參數選 store 後端。

    - ``sqlite:<path>``  → SqliteArtifactStore
    - 其他（資料夾路徑）  → FileArtifactStore
    """
    if store_arg.startswith("sqlite:"):
        return SqliteArtifactStore(store_arg[len("sqlite:"):])
    return FileArtifactStore(store_arg)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="CIM tool registry server")
    parser.add_argument("--port", type=int, default=9000, help="listen port (default 9000)")
    parser.add_argument(
        "--store",
        default="registry-store",
        help="store backend: a folder path, or 'sqlite:<path>' (default ./registry-store)",
    )
    args = parser.parse_args(argv)

    import uvicorn  # noqa: PLC0415

    app = create_app(_build_store(args.store))
    # 只聽 loopback：本期 registry 僅供本機 fleet 模擬 / 內網使用。
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
