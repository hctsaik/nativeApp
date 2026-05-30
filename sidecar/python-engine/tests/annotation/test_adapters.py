from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from plugins.labeling.domain.adapters.coco import export_coco, import_coco_file
from plugins.labeling.domain.adapters.isat import export_isat, import_isat_file
from plugins.labeling.domain.adapters.labelme import export_labelme, import_labelme_file, import_labelme_project_dir
from plugins.labeling.domain.adapters.xanylabeling import XAnyLabelingProjectAdapter
from plugins.labeling.domain.adapters.yolo_detection import export_yolo_detection, import_yolo_detection_dir
from plugins.labeling.domain.adapters.yolo_segmentation import export_yolo_segmentation, import_yolo_segmentation_dir
from plugins.labeling.domain.core.models import (
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


def test_coco_import_reads_bbox_and_polygon(tmp_path: Path) -> None:
    schema = _schema()
    asset = _asset(tmp_path)
    payload = {
        "images": [{"id": 1, "file_name": "dog.png", "width": 100, "height": 80}],
        "categories": [{"id": 7, "name": "dog"}],
        "annotations": [
            {"id": 1, "image_id": 1, "category_id": 7, "bbox": [10, 20, 30, 40], "area": 1200, "segmentation": [], "iscrowd": 0},
            {"id": 2, "image_id": 1, "category_id": 7, "bbox": [1, 1, 9, 9], "area": 40, "segmentation": [[1, 1, 10, 1, 10, 10]], "iscrowd": 0},
        ],
    }
    path = tmp_path / "coco.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    imported, report, unmatched = import_coco_file(path, "ds_1", schema, [asset])

    assert unmatched == []
    assert report.lossless is True
    assert [annotation.geometry_type() for annotation in imported.annotations] == ["bbox", "polygon"]


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


def test_xanylabeling_four_point_rectangle_imports_as_bbox(tmp_path: Path) -> None:
    schema = _schema()
    asset = _asset(tmp_path)
    payload = {
        "version": "4.0.0",
        "flags": {},
        "checked": False,
        "imagePath": "dog.png",
        "imageData": None,
        "imageHeight": 80,
        "imageWidth": 100,
        "shapes": [
            {
                "label": "dog",
                "points": [[10, 20], [40, 20], [40, 60], [10, 60]],
                "group_id": "ann_xany_rect",
                "shape_type": "rectangle",
                "flags": {},
            }
        ],
    }
    path = tmp_path / "xany_rect.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    imported, report = import_labelme_file(path, "ds_1", schema, asset)

    assert report.lossless is True
    bbox = imported.annotations[0].geometry
    assert isinstance(bbox, BBoxGeometry)
    assert bbox.x == 10
    assert bbox.y == 20
    assert bbox.width == 30
    assert bbox.height == 40


def test_isat_round_trip_preserves_polygon_and_bbox_metadata(tmp_path: Path) -> None:
    schema = _schema()
    asset = _asset(tmp_path)
    annotation_set = _annotation_set(asset)

    result = export_isat(annotation_set, schema, {asset.id: asset}, tmp_path / "isat")
    payload = json.loads((tmp_path / "isat" / "asset_1.json").read_text(encoding="utf-8"))
    imported, report = import_isat_file(tmp_path / "isat" / "asset_1.json", "ds_1", schema, asset)

    assert payload["info"]["description"] == "ISAT"
    assert payload["info"]["name"] == "dog.png"
    assert payload["objects"][0]["category"] == "dog"
    assert "bbox" in payload["objects"][0]
    assert "segmentation" in payload["objects"][0]
    assert result.conversion_report.lossless is False
    assert report.warnings == []
    assert [annotation.geometry_type() for annotation in imported.annotations] == ["polygon", "polygon"]


def test_yolo_segmentation_export_normalizes_polygon_and_reports_bbox_loss(tmp_path: Path) -> None:
    schema = _schema()
    asset = _asset(tmp_path)
    annotation_set = _annotation_set(asset)

    result = export_yolo_segmentation(annotation_set, schema, {asset.id: asset}, tmp_path / "yolo_seg")
    label_text = (tmp_path / "yolo_seg" / "labels" / "asset_1.txt").read_text(encoding="utf-8")
    report = json.loads((tmp_path / "yolo_seg" / "conversion_report.json").read_text(encoding="utf-8"))

    assert "0 0.010000 0.012500 0.100000 0.012500 0.100000 0.125000" in label_text
    assert result.conversion_report.lossless is False
    assert "ann_bbox" in report["unsupported_annotations"]


def test_yolo_detection_import_denormalizes_bbox(tmp_path: Path) -> None:
    schema = _schema()
    asset = _asset(tmp_path)
    labels_dir = tmp_path / "yolo_det"
    labels_dir.mkdir()
    (labels_dir / "asset_1.txt").write_text("0 0.250000 0.500000 0.300000 0.500000\n", encoding="utf-8")

    imported, report, unmatched = import_yolo_detection_dir(labels_dir, "ds_1", schema, [asset])

    assert unmatched == []
    bbox = imported.annotations[0].geometry
    assert isinstance(bbox, BBoxGeometry)
    assert bbox.x == 10
    assert bbox.y == 20
    assert bbox.width == 30
    assert bbox.height == 40


def test_yolo_segmentation_import_builds_polygon(tmp_path: Path) -> None:
    schema = _schema()
    asset = _asset(tmp_path)
    labels_dir = tmp_path / "yolo_seg_in"
    labels_dir.mkdir()
    (labels_dir / "dog.txt").write_text("0 0.010000 0.012500 0.100000 0.012500 0.100000 0.125000\n", encoding="utf-8")

    imported, report, unmatched = import_yolo_segmentation_dir(labels_dir, "ds_1", schema, [asset])

    assert unmatched == []
    polygon = imported.annotations[0].geometry
    assert isinstance(polygon, PolygonGeometry)
    assert polygon.rings[0] == [[1.0, 1.0], [10.0, 1.0], [10.0, 10.0]]


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
