from __future__ import annotations

from pathlib import Path

from annotation.adapters.common import write_conversion_report, write_json_artifact
from annotation.core.models import (
    AdapterResult,
    AnnotationSet,
    BBoxGeometry,
    ConversionReport,
    ImageAsset,
    LabelSchema,
    PolygonGeometry,
)


def export_coco(
    annotation_set: AnnotationSet,
    schema: LabelSchema,
    assets: dict[str, ImageAsset],
    output_dir: Path | str,
) -> AdapterResult:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = ConversionReport(target_format_version="coco-1.0")
    category_ids = {label.id: index + 1 for index, label in enumerate(schema.labels)}
    image_ids = {asset_id: index + 1 for index, asset_id in enumerate(sorted(assets))}
    payload = {
        "images": [
            {
                "id": image_ids[asset.id],
                "file_name": Path(asset.uri).name,
                "width": asset.width,
                "height": asset.height,
            }
            for asset in assets.values()
        ],
        "categories": [
            {"id": category_ids[label.id], "name": label.name}
            for label in schema.labels
        ],
        "annotations": [],
    }
    ann_id = 1
    for annotation in annotation_set.annotations:
        category_id = category_ids.get(annotation.label_id or "")
        image_id = image_ids.get(annotation.asset_id)
        if category_id is None or image_id is None:
            report.mark_loss("annotation", f"Skipped annotation {annotation.id}: missing category or image.")
            continue
        if isinstance(annotation.geometry, BBoxGeometry):
            bbox = [
                annotation.geometry.x,
                annotation.geometry.y,
                annotation.geometry.width,
                annotation.geometry.height,
            ]
            area = annotation.geometry.width * annotation.geometry.height
            segmentation = []
        elif isinstance(annotation.geometry, PolygonGeometry):
            ring = annotation.geometry.rings[0]
            xs = [point[0] for point in ring]
            ys = [point[1] for point in ring]
            bbox = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
            area = abs(_polygon_area(ring))
            segmentation = [[coord for point in ring for coord in point]]
        else:
            report.mark_loss("classification", f"COCO export skipped non-geometry annotation {annotation.id}.")
            continue
        payload["annotations"].append(
            {
                "id": ann_id,
                "image_id": image_id,
                "category_id": category_id,
                "bbox": bbox,
                "area": area,
                "segmentation": segmentation,
                "iscrowd": 0,
            }
        )
        ann_id += 1
    report.class_mapping = {label.name: category_ids[label.id] for label in schema.labels}
    artifacts = [
        write_json_artifact(output / "annotations.json", payload),
        write_json_artifact(
            output / "manifest.json",
            {
                "annotation_set_id": annotation_set.id,
                "schema_id": schema.id,
                "format": "coco",
                "class_mapping": report.class_mapping,
            },
        ),
        write_conversion_report(output / "conversion_report.json", report),
    ]
    return AdapterResult(artifact_refs=artifacts, conversion_report=report)


def _polygon_area(points: list[list[float]]) -> float:
    area = 0.0
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        area += x1 * y2 - x2 * y1
    return area / 2.0
