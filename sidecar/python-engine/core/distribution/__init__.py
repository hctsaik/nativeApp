"""Fleet 分發與遠端更新 —— 工具 artifact 的簽章、來源抽象與序列化。

對應 ``docs/platform/fleet-distribution.md`` 的功能 #1。

對外 API（由 ``core.distribution`` 直接匯出）：

Dataclass
    - :class:`ToolArtifact`：完整可分發單位（tool_id/version/channel/content/
      sha256/signature/created_at/author）。
    - :class:`ToolArtifactMeta`：輕量目錄項目（tool_id/version/channel/sha256/
      created_at）。

簽章（``signing``）
    - :func:`content_sha256` / :func:`sign` / :func:`verify`
    - :func:`make_artifact` / :func:`verify_artifact`
    - :func:`get_secret`（讀 ``CIM_DISTRIBUTION_SECRET``）
    - :func:`meta_of`

序列化（``sources``）
    - :func:`artifact_to_dict` / :func:`artifact_from_dict`
    - :func:`meta_to_dict` / :func:`meta_from_dict`

來源（``sources``）
    - :class:`ToolDistributionSource`（ABC）
    - :class:`LocalFsSource`
    - :class:`HttpRegistrySource`

依賴規則：本套件僅依賴 stdlib（+ engine 已使用的 ``urllib.request``）。
``registry_server`` 才依賴 FastAPI；分發核心邏輯維持無第三方相依、可單獨測。
"""

from __future__ import annotations

from core.distribution.signing import (
    ToolArtifact,
    ToolArtifactMeta,
    content_sha256,
    get_secret,
    make_artifact,
    meta_of,
    sign,
    verify,
    verify_artifact,
)
from core.distribution.sources import (
    HttpRegistrySource,
    LocalFsSource,
    ToolDistributionSource,
    artifact_from_dict,
    artifact_to_dict,
    meta_from_dict,
    meta_to_dict,
)

__all__ = [
    # dataclasses
    "ToolArtifact",
    "ToolArtifactMeta",
    # signing
    "content_sha256",
    "sign",
    "verify",
    "make_artifact",
    "verify_artifact",
    "get_secret",
    "meta_of",
    # serialization
    "artifact_to_dict",
    "artifact_from_dict",
    "meta_to_dict",
    "meta_from_dict",
    # sources
    "ToolDistributionSource",
    "LocalFsSource",
    "HttpRegistrySource",
]
