from __future__ import annotations

import json
from pathlib import Path

from annotation.adapters.common import write_conversion_report
from annotation.core.models import (
    AdapterResult,
    AnnotationSet,
    ArtifactRef,
    BBoxGeometry,
    ConversionReport,
    ImageAsset,
    LabelSchema,
)
from annotation.storage.artifacts import sha256_file


def export_yolo_detection(
    annotation_set: AnnotationSet,
    schema: LabelSchema,
    assets: dict[str, ImageAsset],
    output_dir: Path | str,
) -> AdapterResult:
    output = Path(output_dir)
    labels_dir = output / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    report = ConversionReport(target_format_version="yolo-detection")
    class_ids = {label.id: index for index, label in enumerate(schema.labels)}
    report.class_mapping = {label.name: class_ids[label.id] for label in schema.labels}
    lines_by_asset: dict[str, list[str]] = {asset_id: [] for asset_id in assets}

    for annotation in annotation_set.annotations:
        asset = assets.get(annotation.asset_id)
        class_id = class_ids.get(annotation.label_id or "")
        if asset is None or class_id is None:
            report.mark_loss("annotation", f"Skipped annotation {annotation.id}: missing asset or class.")
            continue
        if not isinstance(annotation.geometry, BBoxGeometry):
            report.mark_loss("geometry", f"YOLO detection skipped non-bbox annotation {annotation.id}.")
            report.unsupported_annotations.append(annotation.id)
            continue
        bbox = annotation.geometry
        x_center = (bbox.x + bbox.width / 2) / asset.width
        y_center = (bbox.y + bbox.height / 2) / asset.height
        width = bbox.width / asset.width
        height = bbox.height / asset.height
        lines_by_asset[asset.id].append(
            f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"
        )

    artifacts: list[ArtifactRef] = []
    for asset_id, lines in lines_by_asset.items():
        path = labels_dir / f"{asset_id}.txt"
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        artifacts.append(
            ArtifactRef(
                artifact_id=path.stem,
                uri=path.resolve().as_uri(),
                media_type="text/plain",
                sha256=sha256_file(path),
                size_bytes=path.stat().st_size,
            )
        )
    classes_path = output / "classes.txt"
    classes_path.write_text("\n".join(label.name for label in schema.labels) + "\n", encoding="utf-8")
    artifacts.append(
        ArtifactRef(
            artifact_id="classes",
            uri=classes_path.resolve().as_uri(),
            media_type="text/plain",
            sha256=sha256_file(classes_path),
            size_bytes=classes_path.stat().st_size,
        )
    )
    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "annotation_set_id": annotation_set.id,
                "schema_id": schema.id,
                "format": "yolo-detection",
                "class_mapping": report.class_mapping,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    artifacts.append(
        ArtifactRef(
            artifact_id="manifest",
            uri=manifest_path.resolve().as_uri(),
            media_type="application/json",
            sha256=sha256_file(manifest_path),
            size_bytes=manifest_path.stat().st_size,
        )
    )
    artifacts.append(write_conversion_report(output / "conversion_report.json", report))
    return AdapterResult(artifact_refs=artifacts, conversion_report=report)
