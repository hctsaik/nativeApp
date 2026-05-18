from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from annotation.adapters.coco import export_coco
from annotation.adapters.labelme import export_labelme, import_labelme_file, import_labelme_project_dir
from annotation.adapters.xanylabeling import XAnyLabelingProjectAdapter
from annotation.adapters.yolo_detection import export_yolo_detection
from annotation.core.models import (
    Annotation,
    AnnotationSet,
    BBoxGeometry,
    ClassificationValue,
    ImageAsset,
    LabelDef,
    LabelSchema,
    PolygonGeometry,
)


def _schema() -> LabelSchema:
    return LabelSchema(
        id="schema_1",
        name="animals",
        labels=[
            LabelDef(id="dog", name="dog", allowed_geometry_types=["bbox", "polygon"]),
            LabelDef(id="scene_ok", name="scene_ok", allowed_geometry_types=["classification"]),
        ],
    )


def _asset(tmp_path: Path) -> ImageAsset:
    image_path = tmp_path / "dog.png"
    Image.new("RGB", (100, 80), color=(20, 30, 40)).save(image_path)
    return ImageAsset(
        id="asset_1",
        dataset_id="ds_1",
        uri=str(image_path),
        width=100,
        height=80,
        checksum="abc",
    )


def _annotation_set(asset: ImageAsset) -> AnnotationSet:
    return AnnotationSet(
        id="aset_1",
        dataset_id=asset.dataset_id,
        schema_id="schema_1",
        state="approved",
        annotations=[
            Annotation(
                id="ann_bbox",
                asset_id=asset.id,
                label_id="dog",
                geometry=BBoxGeometry(x=10, y=20, width=30, height=40),
                attributes={"quality": "good"},
            ),
            Annotation(
                id="ann_poly",
                asset_id=asset.id,
                label_id="dog",
                geometry=PolygonGeometry(rings=[[[1, 1], [10, 1], [10, 10]]]),
            ),
            Annotation(
                id="ann_cls",
                asset_id=asset.id,
                label_id="scene_ok",
                classification=[ClassificationValue(label_id="scene_ok")],
            ),
        ],
    )


def test_labelme_round_trip_preserves_bbox_and_polygon(tmp_path: Path) -> None:
    schema = _schema()
    asset = _asset(tmp_path)
    annotation_set = _annotation_set(asset)

    result = export_labelme(annotation_set, schema, {asset.id: asset}, tmp_path / "labelme")
    imported, report = import_labelme_file(tmp_path / "labelme" / "asset_1.json", "ds_1", schema, asset)

    geometry_types = [annotation.geometry_type() for annotation in imported.annotations]
    assert "bbox" in geometry_types
    assert "polygon" in geometry_types
    assert "classification" in geometry_types
    assert (tmp_path / "labelme" / "manifest.json").exists()
    assert (tmp_path / "labelme" / "conversion_report.json").exists()
    assert result.conversion_report.lossless is False
    assert report.warnings == []


def test_yolo_detection_export_normalizes_bbox_and_reports_polygon_loss(tmp_path: Path) -> None:
    schema = _schema()
    asset = _asset(tmp_path)
    annotation_set = _annotation_set(asset)

    result = export_yolo_detection(annotation_set, schema, {asset.id: asset}, tmp_path / "yolo")
    label_text = (tmp_path / "yolo" / "labels" / "asset_1.txt").read_text(encoding="utf-8")
    report = json.loads((tmp_path / "yolo" / "conversion_report.json").read_text(encoding="utf-8"))

    assert "0 0.250000 0.500000 0.300000 0.500000" in label_text
    assert result.conversion_report.lossless is False
    assert "ann_poly" in report["unsupported_annotations"]


def test_coco_export_writes_bbox_and_polygon(tmp_path: Path) -> None:
    schema = _schema()
    asset = _asset(tmp_path)
    annotation_set = _annotation_set(asset)

    export_coco(annotation_set, schema, {asset.id: asset}, tmp_path / "coco")
    payload = json.loads((tmp_path / "coco" / "annotations.json").read_text(encoding="utf-8"))

    assert len(payload["images"]) == 1
    assert len(payload["categories"]) == 2
    assert len(payload["annotations"]) == 2
    assert payload["annotations"][0]["bbox"] == [10, 20, 30, 40]
    assert (tmp_path / "coco" / "manifest.json").exists()


def test_import_labelme_project_dir_matches_by_image_path(tmp_path: Path) -> None:
    schema = _schema()
    asset = _asset(tmp_path)
    annotation_set = _annotation_set(asset)
    labels_dir = tmp_path / "labels"
    export_labelme(annotation_set, schema, {asset.id: asset}, labels_dir)
    # export writes asset_id.json; rename to the image filename to simulate X-AnyLabeling output
    (labels_dir / f"{asset.id}.json").rename(labels_dir / "dog.json")
    # patch imagePath so it matches asset URI filename
    import json as _json
    payload = _json.loads((labels_dir / "dog.json").read_text())
    payload["imagePath"] = "dog.png"
    (labels_dir / "dog.json").write_text(_json.dumps(payload), encoding="utf-8")

    merged, report, unmatched = import_labelme_project_dir(labels_dir, "ds_1", schema, [asset])

    assert unmatched == []
    geometry_types = [a.geometry_type() for a in merged.annotations]
    assert "bbox" in geometry_types
    assert "polygon" in geometry_types


def test_import_labelme_project_dir_reports_unmatched_files(tmp_path: Path) -> None:
    schema = _schema()
    labels_dir = tmp_path / "labels"
    labels_dir.mkdir()
    (labels_dir / "unknown_image.json").write_text(
        '{"imagePath": "no_such_image.png", "shapes": [], "flags": {}}', encoding="utf-8"
    )

    merged, report, unmatched = import_labelme_project_dir(labels_dir, "ds_1", schema, [])

    assert "unknown_image.json" in unmatched
    assert merged.annotations == []
    assert report.lossless is False


def test_xanylabeling_project_preparation_copies_assets_and_writes_manifest(tmp_path: Path) -> None:
    schema = _schema()
    asset = _asset(tmp_path)
    adapter = XAnyLabelingProjectAdapter()

    adapter.prepare_project("ds_1", schema, [asset], tmp_path / "xany")
    manifest = json.loads((tmp_path / "xany" / "manifest.json").read_text(encoding="utf-8"))

    assert (tmp_path / "xany" / "images" / "dog.png").exists()
    assert (tmp_path / "xany" / "classes.txt").read_text(encoding="utf-8").splitlines() == [
        "dog",
        "scene_ok",
    ]
    assert manifest["dataset_id"] == "ds_1"
