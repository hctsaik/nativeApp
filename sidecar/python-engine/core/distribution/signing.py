"""工具 artifact 的雜湊與簽章（純 stdlib，禁第三方相依）。

對應規格 §4 (Artifact 模型) 與 §5.1。

設計重點：
- ``content`` 的雜湊一律對 **canonical JSON** 取 sha256，確保跨機器可重算
  （鍵排序固定、不轉義非 ASCII、分隔符固定）。
- 簽章使用 HMAC-SHA256（共享密鑰 MVP）。這是 MVP 折衷；production 應升級為
  非對稱簽章（Ed25519，``cryptography`` 套件），但 :func:`sign` /
  :func:`verify` / :func:`verify_artifact` 的介面可保持不變。
- 驗章用 :func:`hmac.compare_digest` 常數時間比較，避免 timing side-channel。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# 開發用的固定預設密鑰；未設環境變數時使用，並發出警告。
# 切勿用於 production —— 必須以 CIM_DISTRIBUTION_SECRET 覆蓋。
_DEV_DEFAULT_SECRET = "cim-dev-distribution-secret-do-not-use-in-prod"

_SECRET_ENV = "CIM_DISTRIBUTION_SECRET"


# ---------------------------------------------------------------------------
# Dataclass 模型（規格 §4）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolArtifact:
    """一個工具版本的可分發單位（含完整 content 與簽章）。"""

    tool_id: str           # e.g. module_042
    version: str           # semver
    channel: str           # "dev" | "prod"
    content: dict          # plugin.yaml + *.py 原始碼快照（同 content_json 形狀）
    sha256: str            # canonical-json(content) 的 sha256 hex
    signature: str         # sign(sha256)；驗章用
    created_at: str        # ISO-8601 UTC
    author: str


@dataclass(frozen=True)
class ToolArtifactMeta:
    """輕量目錄項目（不含 content），供 ``list_artifacts`` / catalog 使用。"""

    tool_id: str
    version: str
    channel: str
    sha256: str
    created_at: str


# ---------------------------------------------------------------------------
# 密鑰來源
# ---------------------------------------------------------------------------


def get_secret() -> str:
    """取得簽章密鑰。

    優先讀 ``CIM_DISTRIBUTION_SECRET`` 環境變數；未設時回固定 dev 預設值並警告。
    """
    secret = os.environ.get(_SECRET_ENV)
    if secret:
        return secret
    logger.warning(
        "%s not set — using insecure dev default distribution secret. "
        "Set %s in production.",
        _SECRET_ENV,
        _SECRET_ENV,
    )
    return _DEV_DEFAULT_SECRET


# ---------------------------------------------------------------------------
# 純函式：雜湊 / 簽章 / 驗章
# ---------------------------------------------------------------------------


def _canonical_json(content: dict) -> str:
    """content 的 canonical JSON 字串（鍵排序固定、保留非 ASCII、分隔符固定）。"""
    return json.dumps(
        content,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def content_sha256(content: dict) -> str:
    """對 content 的 canonical JSON 取 sha256，回傳 hex 字串。

    鍵順序不影響結果（canonical JSON 排序鍵）。
    """
    canonical = _canonical_json(content)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sign(sha256_hex: str, secret: str) -> str:
    """以 HMAC-SHA256(secret, sha256_hex) 簽章，回傳 hex 字串。"""
    return hmac.new(
        secret.encode("utf-8"),
        sha256_hex.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify(sha256_hex: str, signature: str, secret: str) -> bool:
    """常數時間比對 signature 是否為 sha256_hex 的合法簽章。"""
    expected = sign(sha256_hex, secret)
    return hmac.compare_digest(expected, signature)


def make_artifact(
    tool_id: str,
    version: str,
    channel: str,
    content: dict,
    author: str,
    secret: str,
) -> ToolArtifact:
    """從 content 建立一個已簽章的 :class:`ToolArtifact`。"""
    sha256_hex = content_sha256(content)
    signature = sign(sha256_hex, secret)
    created_at = datetime.now(timezone.utc).isoformat()
    return ToolArtifact(
        tool_id=tool_id,
        version=version,
        channel=channel,
        content=content,
        sha256=sha256_hex,
        signature=signature,
        created_at=created_at,
        author=author,
    )


def verify_artifact(artifact: ToolArtifact, secret: str) -> bool:
    """重算 content 的 sha256 → 比對 ``artifact.sha256`` → 再驗 signature。

    任一不符即回 ``False``（拒絕安裝未驗證或被竄改的碼）。
    """
    recomputed = content_sha256(artifact.content)
    # 用常數時間比對 sha256，避免 content 竄改的 timing 洩漏
    if not hmac.compare_digest(recomputed, artifact.sha256):
        return False
    return verify(artifact.sha256, artifact.signature, secret)


def meta_of(artifact: ToolArtifact) -> ToolArtifactMeta:
    """從完整 artifact 取輕量目錄項目。"""
    return ToolArtifactMeta(
        tool_id=artifact.tool_id,
        version=artifact.version,
        channel=artifact.channel,
        sha256=artifact.sha256,
        created_at=artifact.created_at,
    )
