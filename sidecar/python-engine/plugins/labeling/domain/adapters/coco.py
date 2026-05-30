from __future__ import annotations

from pathlib import Path

from plugins.labeling.domain.adapters.common import write_conversion_report, write_json_artifact
from plugins.labeling.domain.core.models import (
    Annotation,
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


def import_coco_file(
    input_path: Path | str,
    dataset_id: str,
    schema: LabelSchema,
    assets: list[ImageAsset],
) -> tuple[AnnotationSet, ConversionReport, list[str]]:
    import json

    path = Path(input_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    report = ConversionReport(source_format_version="coco-1.0")
    asset_by_filename = {Path(asset.uri).name: asset for asset in assets}
    image_id_to_asset: dict[int, ImageAsset] = {}
    unmatched: list[str] = []
    for image in payload.get("images", []):
        file_name = Path(image.get("file_name", "")).name
        asset = asset_by_filename.get(file_name)
        if asset is None:
            unmatched.append(file_name)
            report.mark_loss("asset", f"No asset matched for COCO image {file_name!r}.")
            continue
        image_id_to_asset[int(image["id"])] = asset

    label_by_name = {label.name: label for label in schema.labels}
    category_id_to_label = {
        int(category["id"]): label_by_name[category["name"]]
        for category in payload.get("categories", [])
        if category.get("name") in label_by_name
    }

    annotations: list[Annotation] = []
    for item in payload.get("annotations", []):
        asset = image_id_to_asset.get(int(item.get("image_id", -1)))
        label = category_id_to_label.get(int(item.get("category_id", -1)))
        if asset is None or label is None:
            report.mark_loss("annotation", f"Skipped COCO annotation {item.get('id')}: missing asset or label.")
            continue
        segmentation = item.get("segmentation")
        geometry = None
        if isinstance(segmentation, list) and segmentation and isinstance(segmentation[0], list):
            coords = segmentation[0]
            points = [[float(coords[i]), float(coords[i + 1])] for i in range(0, len(coords) - 1, 2)]
            if len(points) >= 3:
                geometry = PolygonGeometry(rings=[points])
        elif isinstance(segmentation, dict):
            report.mark_loss("segmentation", f"COCO RLE segmentation skipped for annotation {item.get('id')}.")
            report.unsupported_annotations.append(str(item.get("id")))
            continue
        if geometry is None:
            bbox = item.get("bbox") or []
            if len(bbox) == 4:
                geometry = BBoxGeometry(x=float(bbox[0]), y=float(bbox[1]), width=float(bbox[2]), height=float(bbox[3]))
            else:
                report.mark_loss("geometry", f"COCO annotation {item.get('id')} has no supported geometry.")
                continue
        annotation = Annotation(
            asset_id=asset.id,
            label_id=label.id,
            geometry=geometry,
            source="imported",
            attributes={"coco_iscrowd": item.get("iscrowd", 0)},
            provenance={"imported_from": path.name},
        )
        if item.get("id") is not None:
            annotation.id = str(item["id"])
        annotations.append(annotation)

    return (
        AnnotationSet(
            dataset_id=dataset_id,
            schema_id=schema.id,
            annotations=annotations,
            source="imported",
            provenance={"adapter": "coco", "source_file": path.name},
        ),
        report,
        unmatched,
    )
