from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import urlparse

from plugins.labeling.domain.adapters.common import write_json_artifact
from plugins.labeling.domain.core.models import AdapterResult, ImageAsset, LabelSchema


class XAnyLabelingProjectAdapter:
    def prepare_project(
        self,
        dataset_id: str,
        schema: LabelSchema,
        assets: list[ImageAsset],
        output_dir: Path | str,
    ) -> AdapterResult:
        root = Path(output_dir)
        images_dir = root / "images"
        labels_dir = root / "labels"
        images_dir.mkdir(parents=True, exist_ok=True)
        labels_dir.mkdir(parents=True, exist_ok=True)
        for asset in assets:
            source = _path_from_uri(asset.uri)
            if source.exists():
                shutil.copy2(source, images_dir / source.name)
        classes_path = root / "classes.txt"
        classes_path.write_text(
            "\n".join(label.name for label in schema.labels) + "\n",
            encoding="utf-8",
        )
        manifest = {
            "dataset_id": dataset_id,
            "schema_id": schema.id,
            "adapter": "x-anylabeling",
            "asset_ids": [asset.id for asset in assets],
            "label_count": len(schema.labels),
            "images_dir": str(images_dir),
            "labels_dir": str(labels_dir),
            "classes_path": str(classes_path),
        }
        artifact = write_json_artifact(root / "manifest.json", manifest)
        return AdapterResult(artifact_refs=[artifact])


def _path_from_uri(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        try:
            return Path.from_uri(uri)
        except AttributeError:
            # Python < 3.13 fallback
            from urllib.request import url2pathname
            return Path(url2pathname(parsed.path))
    return Path(uri)
