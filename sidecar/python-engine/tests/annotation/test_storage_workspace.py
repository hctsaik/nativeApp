from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from annotation.core.models import Annotation, AnnotationSet, BBoxGeometry, LabelDef, LabelSchema
from annotation.storage.workspace import AnnotationWorkspace


def _write_image(path: Path) -> None:
    image = Image.new("RGB", (32, 24), color=(120, 40, 80))
    image.save(path)


def test_workspace_ingests_image_idempotently(tmp_path: Path) -> None:
    workspace = AnnotationWorkspace(tmp_path / "workspace")
    source = tmp_path / "dog.png"
    _write_image(source)
    dataset = workspace.create_dataset("animals", str(tmp_path))

    first = workspace.ingest_image(dataset.id, source)
    second = workspace.ingest_image(dataset.id, source)

    assert first.id == second.id
    assert first.width == 32
    assert first.height == 24
    assert len(workspace.metadata.list_assets(dataset.id)) == 1


def test_workspace_persists_schema_and_canonical_annotation_set(tmp_path: Path) -> None:
    workspace = AnnotationWorkspace(tmp_path / "workspace")
    dataset = workspace.create_dataset("animals", str(tmp_path))
    schema = workspace.save_schema(
        LabelSchema(
            id="schema_1",
            name="animals",
            labels=[LabelDef(id="dog", name="dog", allowed_geometry_types=["bbox"])],
        )
    )
    annotation_set = AnnotationSet(
        id="aset_1",
        dataset_id=dataset.id,
        schema_id=schema.id,
        annotations=[
            Annotation(
                asset_id="asset_1",
                label_id="dog",
                geometry=BBoxGeometry(x=1, y=2, width=3, height=4),
            )
        ],
    )

    canonical_path = workspace.write_canonical_annotation_set(annotation_set)
    stored = workspace.metadata.get_annotation_set(annotation_set.id)

    assert canonical_path.exists()
    assert stored is not None
    assert stored.annotations[0].geometry.to_dict()["type"] == "bbox"
    assert json.loads(canonical_path.read_text(encoding="utf-8"))["id"] == "aset_1"
