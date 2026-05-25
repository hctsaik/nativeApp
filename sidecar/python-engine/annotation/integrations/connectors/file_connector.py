"""
annotation.integrations.connectors.file_connector
---------------------------------------------------
FileConnector — 以本地檔案系統作為「外部系統」的 connector。
適合用於離線標注、從資料夾批次匯入圖片，或整合測試（比 FakeConnector 更接近真實 I/O）。

Profile extra 欄位（均為選用，若不設定則對應功能不可用）：
    image_root_path : str  — list_tasks 掃描的圖片根目錄
    label_file      : str  — load_label_schema 讀取的 label 清單檔（每行一個 label）
    output_path     : str  — push_annotations 輸出結果的目標路徑
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from annotation.integrations.contracts import (
    ConnectorHealth,
    ExportPayload,
    ExternalSystemConnector,
    ExternalTask,
    PaginationToken,
    PushResult,
    RawLabelSchema,
    ResolvedAsset,
)
from annotation.integrations.profiles import IntegrationProfile

# 支援的圖片副檔名（小寫）
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}


class FileConnector(ExternalSystemConnector):
    """
    本地檔案系統 connector。
    所有資產路徑均為本地絕對路徑或相對路徑，不需要網路連線。
    """

    def __init__(self, profile: IntegrationProfile) -> None:
        """
        初始化 FileConnector。
        profile.extra 中的路徑設定（image_root_path / label_file / output_path）
        在此解析為 Path 物件，但不立即驗證存在性（由各方法呼叫時驗證）。
        """
        self._profile = profile
        extra = profile.extra

        self._image_root: Path | None = (
            Path(extra["image_root_path"]) if "image_root_path" in extra else None
        )
        self._label_file: Path | None = (
            Path(extra["label_file"]) if "label_file" in extra else None
        )
        self._output_path: Path | None = (
            Path(extra["output_path"]) if "output_path" in extra else None
        )

    # ------------------------------------------------------------------
    # ExternalSystemConnector interface
    # ------------------------------------------------------------------

    def list_tasks(
        self,
        query: dict,
        pagination_token: PaginationToken,
    ) -> tuple[list[ExternalTask], PaginationToken]:
        """
        掃描 image_root_path 目錄，將每個圖片檔案視為一個 ExternalTask。
        external_id 使用相對於 image_root_path 的路徑字串。
        忽略 query 與 pagination_token（Phase 4 不做分頁）。
        """
        if self._image_root is None:
            raise ValueError(
                "FileConnector.list_tasks 需要 profile.extra['image_root_path']"
            )
        if not self._image_root.exists():
            raise FileNotFoundError(
                f"image_root_path 不存在：{self._image_root}"
            )

        tasks: list[ExternalTask] = []
        for img_path in sorted(self._image_root.rglob("*")):
            if img_path.suffix.lower() in _IMAGE_EXTENSIONS and img_path.is_file():
                rel = img_path.relative_to(self._image_root)
                tasks.append(
                    ExternalTask(
                        external_id=str(rel),
                        image_uri=str(img_path.resolve()),
                        metadata={"size_bytes": img_path.stat().st_size},
                    )
                )

        return tasks, PaginationToken(value=None)

    def resolve_asset(self, task: ExternalTask) -> ResolvedAsset:
        """
        將 task.image_uri 視為本地路徑並驗證存在性。
        回傳 ResolvedAsset(asset_type="local_path", value=絕對路徑)。
        """
        path = Path(task.image_uri)
        if not path.exists():
            raise FileNotFoundError(
                f"resolve_asset 失敗：路徑不存在 {task.image_uri!r}"
            )
        return ResolvedAsset(asset_type="local_path", value=str(path.resolve()))

    def load_label_schema(self) -> RawLabelSchema:
        """
        從 label_file 讀取 label 清單（每行一個 label，忽略空行與 # 開頭的註解）。
        回傳 RawLabelSchema，raw dict 格式為 {"labels": ["cat", "dog", ...]}。
        """
        if self._label_file is None:
            raise ValueError(
                "FileConnector.load_label_schema 需要 profile.extra['label_file']"
            )
        if not self._label_file.exists():
            raise FileNotFoundError(
                f"label_file 不存在：{self._label_file}"
            )

        labels: list[str] = []
        for line in self._label_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                labels.append(stripped)

        return RawLabelSchema(
            raw={"labels": labels},
            source_format="txt_label_list",
        )

    def push_annotations(
        self,
        task_id: str,
        payload: ExportPayload,
        mode: str,
    ) -> PushResult:
        """
        將 payload.data 序列化為 JSON 並寫入 output_path。
        若 output_path 為目錄，則以 task_id 為檔名（斜線轉為底線）寫入該目錄。
        mode 目前僅記錄於 conversion_report，不影響寫入行為。
        """
        if self._output_path is None:
            raise ValueError(
                "FileConnector.push_annotations 需要 profile.extra['output_path']"
            )

        target: Path
        if self._output_path.suffix:
            # output_path 看起來像檔案路徑
            target = self._output_path
        else:
            # output_path 是目錄
            safe_name = task_id.replace("/", "_").replace("\\", "_") + ".json"
            target = self._output_path / safe_name

        target.parent.mkdir(parents=True, exist_ok=True)

        with target.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "task_id": task_id,
                    "format_id": payload.format_id,
                    "mode": mode,
                    "data": payload.data,
                    "conversion_report": payload.conversion_report,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        return PushResult(
            success=True,
            rows_written=1,
            external_ref=str(target),
        )

    def health_check(self) -> ConnectorHealth:
        """
        檢查 image_root_path 是否可達。
        若未設定 image_root_path，改檢查 label_file 或 output_path 的父目錄。
        """
        start = time.monotonic()

        check_path: Path | None = (
            self._image_root
            or (self._label_file.parent if self._label_file else None)
            or (self._output_path.parent if self._output_path else None)
        )

        if check_path is None:
            return ConnectorHealth(
                connected=False,
                error="FileConnector: 未設定任何路徑，無法執行 health check",
            )

        latency_ms = int((time.monotonic() - start) * 1000)

        if check_path.exists():
            return ConnectorHealth(connected=True, latency_ms=latency_ms)
        else:
            return ConnectorHealth(
                connected=False,
                latency_ms=latency_ms,
                error=f"路徑不存在或無法存取：{check_path}",
            )
