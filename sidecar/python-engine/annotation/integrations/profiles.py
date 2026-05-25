"""
annotation.integrations.profiles
----------------------------------
IntegrationProfile dataclass 與載入 / 驗證函式。
Profile 描述如何連接某個外部系統，由 YAML / JSON 檔案設定後傳入各 connector。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FieldMapping:
    """
    外部系統欄位名稱對映到 CIM 內部欄位的設定。
    允許各外部系統使用不同的欄位命名。
    """
    external_task_id: str = "task_id"
    image_uri: str = "image_uri"
    label_class: str | None = None  # 若 None，使用外部 schema 原始欄位名


@dataclass
class IntegrationProfile:
    """
    外部系統整合設定檔。每個 profile 對應一個外部系統的連線組態。

    version       : profile 格式版本（目前為 "1"）
    system_id     : 外部系統唯一識別碼（用於 log / audit）
    tenant_id     : 租戶 ID（對應 ADR-001 row-level isolation）
    connector_type: "oracle" | "rest" | "file" | "fake"
    credential_ref: 指向 CredentialStore 的 key（None = 無需憑證，如 file connector）
    format_policy : 格式錯誤處理策略 "warn_and_skip" | "fail"
    field_mapping : 外部欄位對映設定
    schema_mapping: 原始 schema 對映 dict（connector-specific 格式）

    Phase 4 尚未加入 capability_matrix，保留為空 dict 以利未來擴充。
    """
    version: str
    system_id: str
    tenant_id: str
    connector_type: str       # "oracle" | "rest" | "file" | "fake"
    credential_ref: str | None
    format_policy: str        # "warn_and_skip" | "fail"
    field_mapping: FieldMapping
    schema_mapping: dict      # raw mapping dict，格式由 connector 自行解讀
    extra: dict[str, Any] = field(default_factory=dict)  # connector-specific 額外設定


_REQUIRED_FIELDS = ("version", "system_id", "tenant_id", "connector_type", "format_policy")
_VALID_CONNECTOR_TYPES = {"oracle", "rest", "file", "fake"}
_VALID_FORMAT_POLICIES = {"warn_and_skip", "fail"}


def load_profile(data: dict) -> IntegrationProfile:
    """
    從 dict 建立 IntegrationProfile，並驗證必填欄位。
    缺少必填欄位或值不合法時拋出 ValueError。
    """
    # 檢查必填欄位
    for required in _REQUIRED_FIELDS:
        if required not in data or data[required] is None:
            raise ValueError(f"IntegrationProfile 缺少必填欄位：{required!r}")
        if not str(data[required]).strip():
            raise ValueError(f"IntegrationProfile 欄位 {required!r} 不可為空字串")

    connector_type = data["connector_type"]
    if connector_type not in _VALID_CONNECTOR_TYPES:
        raise ValueError(
            f"不支援的 connector_type：{connector_type!r}，"
            f"有效值：{sorted(_VALID_CONNECTOR_TYPES)}"
        )

    format_policy = data["format_policy"]
    if format_policy not in _VALID_FORMAT_POLICIES:
        raise ValueError(
            f"不支援的 format_policy：{format_policy!r}，"
            f"有效值：{sorted(_VALID_FORMAT_POLICIES)}"
        )

    # 建立 FieldMapping（允許 partial 覆寫，未提供的欄位使用預設值）
    raw_mapping = data.get("field_mapping", {})
    field_mapping = FieldMapping(
        external_task_id=raw_mapping.get("external_task_id", "task_id"),
        image_uri=raw_mapping.get("image_uri", "image_uri"),
        label_class=raw_mapping.get("label_class", None),
    )

    # 收集 connector-specific 額外設定（非標準欄位）
    standard_keys = {
        "version", "system_id", "tenant_id", "connector_type",
        "credential_ref", "format_policy", "field_mapping", "schema_mapping",
    }
    extra = {k: v for k, v in data.items() if k not in standard_keys}

    return IntegrationProfile(
        version=str(data["version"]),
        system_id=str(data["system_id"]),
        tenant_id=str(data["tenant_id"]),
        connector_type=connector_type,
        credential_ref=data.get("credential_ref"),
        format_policy=format_policy,
        field_mapping=field_mapping,
        schema_mapping=data.get("schema_mapping", {}),
        extra=extra,
    )


def load_profile_from_file(path: Path) -> IntegrationProfile:
    """
    從 JSON 檔案載入 IntegrationProfile。
    支援 .json 格式；路徑不存在時拋出 FileNotFoundError。
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Profile 檔案不存在：{path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return load_profile(data)
