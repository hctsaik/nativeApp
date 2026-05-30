from __future__ import annotations

import json
from pathlib import Path

from plugins.labeling.domain.adapters.common import write_conversion_report
from plugins.labeling.domain.core.models import (
    Annotation,
    AnnotationSet,
    AdapterResult,
    AnnotationSet,
    ArtifactRef,
    ConversionReport,
    ImageAsset,
    LabelSchema,
    PolygonGeometry,
)
from plugins.labeling.domain.storage.artifacts import sha256_file


def export_yolo_segmentation(
    annotation_set: AnnotationSet,
    schema: LabelSchema,
    assets: dict[str, ImageAsset],
    output_dir: Path | str,
) -> AdapterResult:
    output = Path(output_dir)
    labels_dir = output / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    report = ConversionReport(target_format_version="yolo-segmentation")
    class_ids = {label.id: index for index, label in enumerate(schema.labels)}
    report.class_mapping = {label.name: class_ids[label.id] for label in schema.labels}
    lines_by_asset: dict[str, list[str]] = {asset_id: [] for asset_id in assets}

    for annotation in annotation_set.annotations:
        asset = assets.get(annotation.asset_id)
        class_id = class_ids.get(annotation.label_id or "")
        if asset is None or class_id is None:
            report.mark_loss("annotation", f"Skipped annotation {annotation.id}: missing asset or class.")
            continue
        if not isinstance(annotation.geometry, PolygonGeometry):
            report.mark_loss("geometry", f"YOLO segmentation skipped non-polygon annotation {annotation.id}.")
            report.unsupported_annotations.append(annotation.id)
            continue
        coords: list[str] = []
        for x, y in annotation.geometry.rings[0]:
            coords.extend([f"{x / asset.width:.6f}", f"{y / asset.height:.6f}"])
        lines_by_asset[asset.id].append(f"{class_id} {' '.join(coords)}")

    artifacts: list[ArtifactRef] = []
    for asset_id, lines in lines_by_asset.items():
        path = labels_dir / f"{asset_id}.txt"
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        artifacts.append(_artifact(path, "text/plain"))

    classes_path = output / "classes.txt"
    classes_path.write_text("\n".join(label.name for label in schema.labels) + "\n", encoding="utf-8")
    artifacts.append(_artifact(classes_path, "text/plain"))

    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "annotation_set_id": annotation_set.id,
                "schema_id": schema.id,
                "format": "yolo-segmentation",
                "class_mapping": report.class_mapping,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    artifacts.append(_artifact(manifest_path, "application/json"))
    artifacts.append(write_conversion_report(output / "conversion_report.json", report))
    return AdapterResult(artifact_refs=artifacts, conversion_report=report)


def import_yolo_segmentation_dir(
    labels_dir: Path | str,
    dataset_id: str,
    schema: LabelSchema,
    assets: list[ImageAsset],
) -> tuple[AnnotationSet, ConversionReport, list[str]]:
    labels_path = Path(labels_dir)
    report = ConversionReport(source_format_version="yolo-segmentation")
    labels_by_index = {index: label for index, label in enumerate(schema.labels)}
    asset_by_key = {asset.id: asset for asset in assets}
    asset_by_key.update({Path(asset.uri).stem: asset for asset in assets})
    annotations: list[Annotation] = []
    unmatched: list[str] = []

    for txt in sorted(labels_path.glob("*.txt")):
        if txt.name == "classes.txt":
            continue
        asset = asset_by_key.get(txt.stem)
        if asset is None:
            unmatched.append(txt.name)
            report.mark_loss("asset", f"No asset matched for YOLO label file {txt.name}.")
            continue
        for line_no, raw in enumerate(txt.read_text(encoding="utf-8").splitlines(), start=1):
            parts = raw.split()
            if len(parts) < 7 or len(parts[1:]) % 2 != 0:
                report.mark_loss("row", f"Skipped malformed YOLO segmentation row {txt.name}:{line_no}.")
                continue
            class_id = int(float(parts[0]))
            label = labels_by_index.get(class_id)
            if label is None:
                report.mark_loss("label", f"Skipped unknown YOLO class id {class_id}.")
                continue
            coords = [float(v) for v in parts[1:]]
            points = [
                [coords[i] * asset.width, coords[i + 1] * asset.height]
                for i in range(0, len(coords), 2)
            ]
            annotations.append(
                Annotation(
                    asset_id=asset.id,
                    label_id=label.id,
                    geometry=PolygonGeometry(rings=[points]),
                    source="imported",
                    provenance={"imported_from": txt.name},
                )
            )

    return (
        AnnotationSet(
            dataset_id=dataset_id,
            schema_id=schema.id,
            annotations=annotations,
            source="imported",
            provenance={"adapter": "yolo-segmentation", "source_dir": str(labels_path)},
        ),
        report,
        unmatched,
    )


def _artifact(path: Path, media_type: str) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=path.stem,
        uri=path.resolve().as_uri(),
        media_type=media_type,
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
    )
