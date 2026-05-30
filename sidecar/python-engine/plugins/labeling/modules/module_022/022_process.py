from __future__ import annotations

"""
022_process.py — Tenant 管理輔助函式

本模組不需要 engine execute 流程。
input 頁直接呼叫 AnnotationService。
"""

import os
from pathlib import Path


def get_service():
    """取得 AnnotationService 實例。"""
    from plugins.labeling.domain.services import AnnotationService
    from plugins.labeling.domain.storage.workspace import AnnotationWorkspace
    ws_path = Path(os.environ.get("CIM_LOG_DIR", "/tmp")) / "annotation_workspace"
    return AnnotationService(AnnotationWorkspace(ws_path))


def execute_logic(params: dict) -> dict:
    """module_022 不使用 engine execute 流程，僅回傳空結果。"""
    return {"mode": "idle"}
