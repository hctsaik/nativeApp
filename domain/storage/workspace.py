from __future__ import annotations

import json
from pathlib import Path

from plugins.labeling.domain.core.models import AnnotationSet, Dataset, ImageAsset, LabelSchema
from plugins.labeling.domain.storage.artifacts import LocalArtifactStore, sha256_file
from plugins.labeling.domain.storage.sqlite_store import SQLiteMetadataStore


class AnnotationWorkspace:
    """
    工作區管理：負責本地目錄結構（ZIP 解壓後的 images、舊版標注集 canonical JSON）。
    metadata 使用 SQLiteMetadataStore，同時支援新的三張表與保留的舊版 schema/dataset 表。
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.metadata = SQLiteMetadataStore(self.root / "catalog.sqlite")
        self.artifacts = LocalArtifactStore(self.root)

    # ── 工作區目錄管理（ZIP 解壓後的 images 存放位置） ─────────────────────

    def task_images_dir(self, task_id: str) -> Path:
        """回傳指定 task 的 images 目錄（不自動建立）。"""
        return self.root / "tasks" / task_id / "images"

    def ensure_task_images_dir(self, task_id: str) -> Path:
        """確保 task 的 images 目錄存在並回傳路徑。"""
        d = self.task_images_dir(task_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def update_task_delivery(self, task_id: str, delivery_result: dict) -> None:
        """將回饋結果存入資料庫的 delivery_status 欄位。"""
        self.metadata.update_task_delivery(task_id, delivery_result)

    # ── 舊版 Dataset / Asset / Schema 介面（FormatRegistry 相容用） ─────────

    def create_dataset(self, name: str, root_uri: str, metadata: dict | None = None) -> Dataset:
        dataset = Dataset(name=name, root_uri=root_uri, metadata=metadata or {})
        return self.metadata.save_dataset(dataset)

    def save_schema(self, schema: LabelSchema) -> LabelSchema:
        return self.metadata.save_schema(schema)

    def ingest_image(self, dataset_id: str, image_path: Path | str, copy: bool = True) -> ImageAsset:
        source = Path(image_path)
        checksum = sha256_file(source)
        existing = self.metadata.find_asset_by_checksum(dataset_id, checksum)
        if existing is not None:
            return existing
        from PIL import Image  # lazy import — only needed by legacy ingest_image
        with Image.open(source) as img:
            width, height = img.size
        asset_id = f"asset_{checksum[:12]}"
        artifact = self.artifacts.put_file(
            source,
            f"datasets/{dataset_id}/assets/originals",
            media_type=_image_media_type(source),
            artifact_id=asset_id,
            copy=copy,
        )
        asset = ImageAsset(
            id=asset_id,
            dataset_id=dataset_id,
            uri=artifact.uri,
            width=width,
            height=height,
            checksum=checksum,
        )
        return self.metadata.save_asset(asset)

    def write_canonical_annotation_set(self, annotation_set: AnnotationSet) -> Path:
        target = (
            self.root
            / "datasets"
            / annotation_set.dataset_id
            / "annotations"
            / annotation_set.id
            / "canonical.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(annotation_set.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        manifest = target.parent / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "annotation_set_id": annotation_set.id,
                    "dataset_id": annotation_set.dataset_id,
                    "schema_id": annotation_set.schema_id,
                    "version": annotation_set.version,
                    "state": annotation_set.state,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self.metadata.save_annotation_set(annotation_set)
        return target


def _image_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".bmp":
        return "image/bmp"
    return "application/octet-stream"
