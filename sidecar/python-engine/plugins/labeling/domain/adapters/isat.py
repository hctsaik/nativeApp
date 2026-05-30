from __future__ import annotations

import json
from pathlib import Path

from plugins.labeling.domain.adapters.common import write_conversion_report, write_json_artifact
from plugins.labeling.domain.core.models import (
    AdapterResult,
    Annotation,
    AnnotationSet,
    BBoxGeometry,
    ConversionReport,
    ImageAsset,
    LabelSchema,
    PolygonGeometry,
)


def export_isat(
    annotation_set: AnnotationSet,
    schema: LabelSchema,
    assets: dict[str, ImageAsset],
    output_dir: Path | str,
) -> AdapterResult:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = ConversionReport(target_format_version="isat-json")
    label_names = {label.id: label.name for label in schema.labels}
    artifacts = []
    grouped: dict[str, list[Annotation]] = {}
    for annotation in annotation_set.annotations:
        grouped.setdefault(annotation.asset_id, []).append(annotation)

    for asset_id, annotations in grouped.items():
        asset = assets[asset_id]
        payload = _asset_to_isat_payload(asset, annotations, label_names, report)
        artifacts.append(write_json_artifact(output / f"{asset_id}.json", payload))

    artifacts.append(
        write_json_artifact(
            output / "manifest.json",
            {
                "annotation_set_id": annotation_set.id,
                "schema_id": schema.id,
                "format": "isat",
                "asset_ids": sorted(grouped),
            },
        )
    )
    artifacts.append(write_conversion_report(output / "conversion_report.json", report))
    return AdapterResult(artifact_refs=artifacts, conversion_report=report)


def import_isat_file(
    input_path: Path | str,
    dataset_id: str,
    schema: LabelSchema,
    asset: ImageAsset,
) -> tuple[AnnotationSet, ConversionReport]:
    path = Path(input_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    report = ConversionReport(source_format_version="isat-json")
    label_by_name = {label.name: label for label in schema.labels}
    annotations: list[Annotation] = []

    for obj in payload.get("objects", []):
        label = label_by_name.get(obj.get("category"))
        if label is None:
            report.mark_loss("label", f"Unknown ISAT category skipped: {obj.get('category')}")
            report.unsupported_annotations.append(str(obj.get("category", "<missing-category>")))
            continue
        segmentation = obj.get("segmentation") or []
        if len(segmentation) >= 3:
            geometry = PolygonGeometry(rings=[segmentation])
        else:
            bbox = obj.get("bbox") or []
            if len(bbox) == 4:
                x_min, y_min, x_max, y_max = [float(v) for v in bbox]
                geometry = BBoxGeometry(x=x_min, y=y_min, width=x_max - x_min, height=y_max - y_min)
                report.mark_loss("segmentation", "Imported ISAT bbox without polygon segmentation.")
            else:
                report.mark_loss("geometry", f"Unsupported ISAT object skipped: {obj.get('category')}")
                continue

        annotation = Annotation(
            asset_id=asset.id,
            label_id=label.id,
            geometry=geometry,
            source="imported",
            attributes={
                "isat_group": obj.get("group"),
                "isat_layer": obj.get("layer"),
                "isat_iscrowd": obj.get("iscrowd", False),
            },
            provenance={"imported_from": path.name},
        )
        if obj.get("group") not in (None, ""):
            annotation.id = str(obj["group"])
        annotations.append(annotation)

    return (
        AnnotationSet(
            dataset_id=dataset_id,
            schema_id=schema.id,
            annotations=annotations,
            source="imported",
            provenance={"adapter": "isat", "source_file": path.name},
        ),
        report,
    )


def import_isat_project_dir(
    labels_dir: Path | str,
    dataset_id: str,
    schema: LabelSchema,
    assets: list[ImageAsset],
) -> tuple[AnnotationSet, ConversionReport, list[str]]:
    labels_path = Path(labels_dir)
    asset_by_filename = {Path(asset.uri).name: asset for asset in assets}
    json_files = sorted(p for p in labels_path.glob("*.json") if p.name not in {"manifest.json", "conversion_report.json"})
    all_annotations: list[Annotation] = []
    aggregated = ConversionReport(source_format_version="isat-json")
    unmatched: list[str] = []

    for json_file in json_files:
        payload = json.loads(json_file.read_text(encoding="utf-8"))
        image_name = Path(payload.get("info", {}).get("name", json_file.stem)).name
        asset = asset_by_filename.get(image_name)
        if asset is None:
            unmatched.append(json_file.name)
            aggregated.mark_loss("asset", f"No asset matched for {json_file.name} (name={image_name!r})")
            continue
        partial_set, report = import_isat_file(json_file, dataset_id, schema, asset)
        all_annotations.extend(partial_set.annotations)
        if not report.lossless:
            aggregated.lossless = False
        aggregated.warnings.extend(report.warnings)
        aggregated.dropped_fields.extend(item for item in report.dropped_fields if item not in aggregated.dropped_fields)
        aggregated.unsupported_annotations.extend(report.unsupported_annotations)

    return (
        AnnotationSet(
            dataset_id=dataset_id,
            schema_id=schema.id,
            annotations=all_annotations,
            source="imported",
            provenance={"adapter": "isat", "source_dir": str(labels_path)},
        ),
        aggregated,
        unmatched,
    )


def prepare_isat_project(
    dataset_id: str,
    schema: LabelSchema,
    assets: list[ImageAsset],
    output_dir: Path | str,
) -> AdapterResult:
    import shutil
    from urllib.parse import urlparse

    root = Path(output_dir)
    images_dir = root / "images"
    ann_dir = root / "annotations"
    images_dir.mkdir(parents=True, exist_ok=True)
    ann_dir.mkdir(parents=True, exist_ok=True)
    for asset in assets:
        source = _path_from_uri(asset.uri, urlparse)
        if source.exists():
            shutil.copy2(source, images_dir / source.name)
    categories_path = root / "categories.txt"
    categories_path.write_text("\n".join(label.name for label in schema.labels) + "\n", encoding="utf-8")
    manifest = {
        "dataset_id": dataset_id,
        "schema_id": schema.id,
        "adapter": "isat",
        "asset_ids": [asset.id for asset in assets],
        "label_count": len(schema.labels),
        "images_dir": str(images_dir),
        "annotations_dir": str(ann_dir),
        "categories_path": str(categories_path),
    }
    return AdapterResult(artifact_refs=[write_json_artifact(root / "manifest.json", manifest)])


def _asset_to_isat_payload(
    asset: ImageAsset,
    annotations: list[Annotation],
    label_names: dict[str, str],
    report: ConversionReport,
) -> dict:
    objects = []
    for index, annotation in enumerate(annotations, start=1):
        label_name = label_names.get(annotation.label_id or "")
        if not label_name:
            report.mark_loss("label_id", f"Unknown label skipped: {annotation.label_id}")
            continue
        if isinstance(annotation.geometry, PolygonGeometry):
            segmentation = annotation.geometry.rings[0]
            bbox = _bbox_from_points(segmentation)
            area = abs(_polygon_area(segmentation))
        elif isinstance(annotation.geometry, BBoxGeometry):
            bbox = [
                annotation.geometry.x,
                annotation.geometry.y,
                annotation.geometry.x + annotation.geometry.width,
                annotation.geometry.y + annotation.geometry.height,
            ]
            segmentation = [
                [bbox[0], bbox[1]],
                [bbox[2], bbox[1]],
                [bbox[2], bbox[3]],
                [bbox[0], bbox[3]],
            ]
            area = annotation.geometry.width * annotation.geometry.height
            report.mark_loss("bbox", f"ISAT exported bbox annotation {annotation.id} as rectangle segmentation.")
        else:
            report.mark_loss("classification", f"ISAT skipped non-geometry annotation {annotation.id}.")
            continue
        objects.append(
            {
                "category": label_name,
                "group": index,
                "segmentation": segmentation,
                "area": area,
                "layer": float(index),
                "bbox": bbox,
                "iscrowd": False,
                "note": annotation.attributes.get("note", ""),
            }
        )
    return {
        "info": {
            "description": "ISAT",
            "folder": str(Path(asset.uri).parent),
            "name": Path(asset.uri).name,
            "width": asset.width,
            "height": asset.height,
            "depth": 3,
            "note": "",
        },
        "objects": objects,
    }


def _bbox_from_points(points: list[list[float]]) -> list[float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _polygon_area(points: list[list[float]]) -> float:
    area = 0.0
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        area += x1 * y2 - x2 * y1
    return area / 2.0


def _path_from_uri(uri: str, urlparse_func) -> Path:
    parsed = urlparse_func(uri)
    if parsed.scheme == "file":
        try:
            return Path.from_uri(uri)
        except AttributeError:
            from urllib.request import url2pathname

            return Path(url2pathname(parsed.path))
    return Path(uri)

