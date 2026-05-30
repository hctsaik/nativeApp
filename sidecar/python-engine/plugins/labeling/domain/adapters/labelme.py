from __future__ import annotations

import json
from pathlib import Path

from plugins.labeling.domain.adapters.common import write_conversion_report, write_json_artifact
from plugins.labeling.domain.core.models import (
    AdapterResult,
    Annotation,
    AnnotationSet,
    BBoxGeometry,
    ClassificationValue,
    ConversionReport,
    ImageAsset,
    LabelSchema,
    PolygonGeometry,
)


def export_labelme(
    annotation_set: AnnotationSet,
    schema: LabelSchema,
    assets: dict[str, ImageAsset],
    output_dir: Path | str,
) -> AdapterResult:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = ConversionReport(target_format_version="labelme-5-compatible")
    artifacts = []
    grouped: dict[str, list[Annotation]] = {}
    for annotation in annotation_set.annotations:
        grouped.setdefault(annotation.asset_id, []).append(annotation)

    for asset_id, annotations in grouped.items():
        asset = assets[asset_id]
        payload = _asset_to_labelme_payload(asset, annotations, schema, report)
        artifacts.append(write_json_artifact(output / f"{asset_id}.json", payload))

    artifacts.append(
        write_json_artifact(
            output / "manifest.json",
            {
                "annotation_set_id": annotation_set.id,
                "schema_id": schema.id,
                "format": "labelme",
                "asset_ids": sorted(grouped),
            },
        )
    )
    artifacts.append(write_conversion_report(output / "conversion_report.json", report))
    return AdapterResult(artifact_refs=artifacts, conversion_report=report)


def import_labelme_file(
    input_path: Path | str,
    dataset_id: str,
    schema: LabelSchema,
    asset: ImageAsset,
) -> tuple[AnnotationSet, ConversionReport]:
    path = Path(input_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    report = ConversionReport(source_format_version="labelme-5-compatible")
    annotations: list[Annotation] = []
    label_by_name = {label.name: label for label in schema.labels}
    for shape in payload.get("shapes", []):
        label = label_by_name.get(shape.get("label"))
        if label is None:
            report.lossless = False
            report.unsupported_annotations.append(shape.get("label", "<missing-label>"))
            report.warnings.append(f"Unknown label skipped: {shape.get('label')}")
            continue
        shape_type = shape.get("shape_type")
        points = shape.get("points") or []
        metadata = shape.get("flags") or {}
        if shape_type == "rectangle" and len(points) >= 2:
            # LabelMe uses 2 diagonal points; X-AnyLabeling uses 4 corner points.
            # Use min/max over all provided points so both formats work correctly.
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            geometry = BBoxGeometry(
                x=min(xs),
                y=min(ys),
                width=max(xs) - min(xs),
                height=max(ys) - min(ys),
            )
        elif shape_type == "polygon" and len(points) >= 3:
            geometry = PolygonGeometry(rings=[points])
        else:
            report.lossless = False
            report.unsupported_annotations.append(str(shape.get("label", shape_type)))
            report.warnings.append(f"Unsupported LabelMe shape skipped: {shape_type}")
            continue
        annotation = Annotation(
            asset_id=asset.id,
            label_id=label.id,
            geometry=geometry,
            source="imported",
            confidence=metadata.get("confidence"),
            attributes=metadata.get("attributes", {}),
            provenance={"imported_from": path.name},
        )
        imported_id = metadata.get("annotation_id") or shape.get("group_id")
        if imported_id:
            annotation.id = str(imported_id)
        annotations.append(annotation)

    for label_name in payload.get("flags", {}).get("classification_labels", []):
        label = label_by_name.get(label_name)
        if label is None:
            report.lossless = False
            report.warnings.append(f"Unknown classification label skipped: {label_name}")
            continue
        annotations.append(
            Annotation(
                asset_id=asset.id,
                label_id=label.id,
                geometry=None,
                classification=[ClassificationValue(label_id=label.id)],
                source="imported",
                provenance={"imported_from": path.name},
            )
        )

    return (
        AnnotationSet(
            dataset_id=dataset_id,
            schema_id=schema.id,
            annotations=annotations,
            source="imported",
            provenance={"adapter": "labelme", "source_file": path.name},
        ),
        report,
    )


def _asset_to_labelme_payload(
    asset: ImageAsset,
    annotations: list[Annotation],
    schema: LabelSchema,
    report: ConversionReport,
) -> dict:
    label_names = {label.id: label.name for label in schema.labels}
    shapes = []
    classification_labels = []
    for annotation in annotations:
        label_name = label_names.get(annotation.label_id or "")
        if not label_name:
            report.mark_loss("label_id", f"Unknown label skipped: {annotation.label_id}")
            continue
        if isinstance(annotation.geometry, BBoxGeometry):
            shape = {
                "label": label_name,
                "points": [
                    [annotation.geometry.x, annotation.geometry.y],
                    [
                        annotation.geometry.x + annotation.geometry.width,
                        annotation.geometry.y + annotation.geometry.height,
                    ],
                ],
                "group_id": annotation.id,
                "description": "",
                "shape_type": "rectangle",
                "flags": _annotation_flags(annotation),
            }
            shapes.append(shape)
        elif isinstance(annotation.geometry, PolygonGeometry):
            shapes.append(
                {
                    "label": label_name,
                    "points": annotation.geometry.rings[0],
                    "group_id": annotation.id,
                    "description": "",
                    "shape_type": "polygon",
                    "flags": _annotation_flags(annotation),
                }
            )
        elif annotation.classification:
            classification_labels.append(label_name)
            report.mark_loss("classification", "Image classification is stored in LabelMe flags.")
        else:
            report.lossless = False
            report.unsupported_annotations.append(annotation.id)
            report.warnings.append(f"Unsupported annotation skipped: {annotation.id}")

    return {
        "version": "5.0.1",
        "flags": {"classification_labels": classification_labels},
        "shapes": shapes,
        "imagePath": Path(asset.uri).name,
        "imageData": None,
        "imageHeight": asset.height,
        "imageWidth": asset.width,
    }


def import_labelme_project_dir(
    labels_dir: Path | str,
    dataset_id: str,
    schema: LabelSchema,
    assets: list[ImageAsset],
) -> tuple[AnnotationSet, ConversionReport, list[str]]:
    """Import all LabelMe JSON files from a labels directory.

    Matches each JSON to an asset by comparing the JSON's imagePath field
    (filename only) against the asset URI filename. Returns a merged
    AnnotationSet, an aggregated ConversionReport, and a list of JSON paths
    that could not be matched to any asset (unmatched).
    """
    labels_path = Path(labels_dir)
    asset_by_filename = {Path(asset.uri).name: asset for asset in assets}
    _SKIP = {"manifest.json", "conversion_report.json"}
    json_files = sorted(p for p in labels_path.glob("*.json") if p.name not in _SKIP)

    all_annotations: list[Annotation] = []
    aggregated = ConversionReport(source_format_version="labelme-5-compatible")
    unmatched: list[str] = []

    for json_file in json_files:
        payload = json.loads(json_file.read_text(encoding="utf-8"))
        image_path_field = payload.get("imagePath", "")
        image_name = Path(image_path_field).name if image_path_field else json_file.stem
        asset = asset_by_filename.get(image_name)
        if asset is None:
            unmatched.append(json_file.name)
            aggregated.lossless = False
            aggregated.warnings.append(f"No asset matched for {json_file.name} (imagePath={image_path_field!r})")
            continue
        partial_set, report = import_labelme_file(json_file, dataset_id, schema, asset)
        all_annotations.extend(partial_set.annotations)
        if not report.lossless:
            aggregated.lossless = False
        aggregated.warnings.extend(report.warnings)
        aggregated.unsupported_annotations.extend(report.unsupported_annotations)

    annotation_set = AnnotationSet(
        dataset_id=dataset_id,
        schema_id=schema.id,
        annotations=all_annotations,
        source="imported",
        provenance={"adapter": "labelme", "source_dir": str(labels_path)},
    )
    return annotation_set, aggregated, unmatched


def _annotation_flags(annotation: Annotation) -> dict:
    return {
        "annotation_id": annotation.id,
        "source": annotation.source,
        "confidence": annotation.confidence,
        "attributes": annotation.attributes,
        "version": annotation.version,
    }
