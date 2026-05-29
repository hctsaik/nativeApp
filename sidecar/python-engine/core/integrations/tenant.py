"""
platform.tenant
---------------
外部系統連線設定（Tenant/Integration Profile）。

SystemTenant 描述已向平台註冊的外部系統，是連接器層的核心設定物件。
此概念與業務領域無關，任何需要對接外部系統的功能模組都可以使用。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SystemTenant:
    """
    已向平台註冊的外部系統連線設定。

    tenant_id        : 平台核發的 UUID（Primary Key）
    system_name      : 外部系統的唯一識別名稱
    server_host_name : 外部系統的 API Base URL（不含末尾斜線）
    target_format    : 此系統期望的資料格式（如 'coco', 'yolo-detection'）
    api_token        : API 存取金鑰；None 表示不需驗證
    """
    tenant_id: str
    system_name: str
    server_host_name: str
    target_format: str
    api_token: str | None = None


_REQUIRED_FIELDS = ("tenant_id", "system_name", "server_host_name", "target_format")


def load_tenant(data: dict) -> SystemTenant:
    """
    從 dict 建立 SystemTenant，並驗證必填欄位。
    缺少必填欄位或值為空時拋出 ValueError。
    """
    for required in _REQUIRED_FIELDS:
        if required not in data or data[required] is None:
            raise ValueError(f"SystemTenant 缺少必填欄位：{required!r}")
        if not str(data[required]).strip():
            raise ValueError(f"SystemTenant 欄位 {required!r} 不可為空字串")

    return SystemTenant(
        tenant_id=str(data["tenant_id"]),
        system_name=str(data["system_name"]),
        server_host_name=str(data["server_host_name"]).rstrip("/"),
        target_format=str(data["target_format"]),
        api_token=data.get("api_token"),
    )


def load_tenant_from_file(path: Path) -> SystemTenant:
    """從 JSON 檔案載入 SystemTenant。路徑不存在時拋出 FileNotFoundError。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Tenant 設定檔不存在：{path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return load_tenant(data)
