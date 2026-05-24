from __future__ import annotations

from pathlib import Path
from typing import Any

from annotation.adapters.coco import export_coco, import_coco_file
from annotation.adapters.isat import export_isat, import_isat_file, import_isat_project_dir, prepare_isat_project
from annotation.adapters.labeling_runtime import detect_labeling_tool, launch_labeling_project
from annotation.adapters.labelme import export_labelme, import_labelme_file, import_labelme_project_dir
from annotation.adapters.xanylabeling import XAnyLabelingProjectAdapter
from annotation.adapters.xanylabeling_runtime import detect_xanylabeling, launch_xanylabeling_project
from annotation.adapters.yolo_detection import export_yolo_detection, import_yolo_detection_dir
from annotation.adapters.yolo_segmentation import export_yolo_segmentation, import_yolo_segmentation_dir
from annotation.core.errors import ConflictError, NotFoundError, ValidationFailedError
from annotation.core.models import (
    AdapterResult,
    Annotation,
    AnnotationSet,
    AttributeDef,
    BBoxGeometry,
    ClassificationValue,
    LabelDef,
    LabelSchema,
    PolygonGeometry,
    new_id,
)
from annotation.core.states import apply_review_decision, transition_annotation_set
from annotation.core.validation import validate_annotation_set
from annotation.storage.workspace import AnnotationWorkspace


class AnnotationService:
    def __init__(self, workspace: AnnotationWorkspace) -> None:
        self.workspace = workspace

    def create_dataset(self, name: str, root_uri: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.workspace.create_dataset(name, root_uri, metadata).to_dict()

    def list_datasets(self) -> list[dict[str, Any]]:
        return [dataset.to_dict() for dataset in self.workspace.metadata.list_datasets()]

    def ingest_assets(self, dataset_id: str, image_paths: list[str], copy: bool = True) -> dict[str, Any]:
        self._require_dataset(dataset_id)
        assets = [self.workspace.ingest_image(dataset_id, path, copy=copy).to_dict() for path in image_paths]
        return {"dataset_id": dataset_id, "assets": assets}

    def create_schema(
        self,
        name: str,
        labels: list[dict[str, Any]],
        attribute_schema: list[dict[str, Any]] | None = None,
        version: str = "1.0",
        schema_id: str | None = None,
    ) -> dict[str, Any]:
        schema = LabelSchema(
            id=schema_id or new_id("schema"),
            name=name,
            version=version,
            labels=[
                LabelDef(
                    id=str(item["id"]),
                    name=str(item.get("name", item["id"])),
                    allowed_geometry_types=list(item.get("allowed_geometry_types", ["bbox"])),
                    color=item.get("color"),
                    required_attributes=list(item.get("required_attributes", [])),
                    domain_attributes=dict(item.get("domain_attributes", {})),
                )
                for item in labels
            ],
            attribute_schema=[AttributeDef(**item) for item in (attribute_schema or [])],
        )
        return self.workspace.save_schema(schema).to_dict()

    def get_schema(self, schema_id: str) -> dict[str, Any]:
        return self._require_schema(schema_id).to_dict()

    def create_annotation_set(
        self,
        dataset_id: str,
        schema_id: str,
        annotations: list[dict[str, Any]] | None = None,
        source: str = "human",
        created_by: str | None = None,
    ) -> dict[str, Any]:
        self._require_dataset(dataset_id)
        self._require_schema(schema_id)
        annotation_set = AnnotationSet(
            dataset_id=dataset_id,
            schema_id=schema_id,
            annotations=[_annotation_from_payload(item) for item in (annotations or [])],
            source=source,  # type: ignore[arg-type]
            created_by=created_by,
        )
        self.workspace.write_canonical_annotation_set(annotation_set)
        return annotation_set.to_dict()

    def get_asset_annotations(self, annotation_set_id: str, asset_id: str | None = None) -> dict[str, Any]:
        annotation_set = self._require_annotation_set(annotation_set_id)
        annotations = annotation_set.annotations
        if asset_id is not None:
            annotations = [annotation for annotation in annotations if annotation.asset_id == asset_id]
        return {
            "annotation_set_id": annotation_set.id,
            "annotations": [annotation.to_dict() for annotation in annotations],
        }

    def get_task(self, task_id: str) -> dict[str, Any]:
        annotation_set = self._require_annotation_set(task_id)
        return {
            "task_id": annotation_set.id,
            "task_type": "annotation_set",
            "annotation_set": annotation_set.to_dict(),
        }

    def list_tasks(self, dataset_id: str | None = None) -> list[dict[str, Any]]:
        if dataset_id is not None:
            self._require_dataset(dataset_id)
        return [
            {
                "task_id": annotation_set.id,
                "task_type": "annotation_set",
                "dataset_id": annotation_set.dataset_id,
                "schema_id": annotation_set.schema_id,
                "state": annotation_set.state,
                "version": annotation_set.version,
            }
            for annotation_set in self.workspace.metadata.list_annotation_sets(dataset_id)
        ]

    def upsert_annotations(
        self,
        annotation_set_id: str,
        annotations: list[dict[str, Any]],
        base_version: int | None = None,
        replace: bool = True,
    ) -> dict[str, Any]:
        annotation_set = self._require_annotation_set(annotation_set_id)
        if annotation_set.state == "approved":
            raise ConflictError(
                "Approved annotation sets cannot be overwritten.",
                {"annotation_set_id": annotation_set.id, "state": annotation_set.state},
            )
        if base_version is not None and annotation_set.version != base_version:
            raise ConflictError(
                "Annotation set version conflict.",
                {
                    "annotation_set_id": annotation_set.id,
                    "expected_version": base_version,
                    "actual_version": annotation_set.version,
                },
            )
        incoming = [_annotation_from_payload(item) for item in annotations]
        if replace:
            annotation_set.annotations = incoming
        else:
            by_id = {annotation.id: annotation for annotation in annotation_set.annotations}
            for annotation in incoming:
                by_id[annotation.id] = annotation
            annotation_set.annotations = list(by_id.values())
        annotation_set.version += 1
        self.workspace.write_canonical_annotation_set(annotation_set)
        return annotation_set.to_dict()

    def validate_set(self, annotation_set_id: str) -> dict[str, Any]:
        annotation_set = self._require_annotation_set(annotation_set_id)
        schema = self._require_schema(annotation_set.schema_id)
        assets = {asset.id: asset for asset in self.workspace.metadata.list_assets(annotation_set.dataset_id)}
        issues = validate_annotation_set(annotation_set, schema, assets)
        return {
            "ok": not issues,
            "annotation_set_id": annotation_set.id,
            "issues": [issue.to_dict() for issue in issues],
        }

    def submit_for_review(self, annotation_set_id: str) -> dict[str, Any]:
        annotation_set = self._require_annotation_set(annotation_set_id)
        issues = self.validate_set(annotation_set_id)["issues"]
        if issues:
            raise ValidationFailedError(issues)
        transition_annotation_set(annotation_set, "submitted")
        self.workspace.write_canonical_annotation_set(annotation_set)
        return annotation_set.to_dict()

    def review_task(self, annotation_set_id: str, decision: str, actor_id: str, comment: str = "") -> dict[str, Any]:
        annotation_set = self._require_annotation_set(annotation_set_id)
        review = apply_review_decision(annotation_set, decision, actor_id, comment)
        self.workspace.metadata.save_review_decision(review)
        self.workspace.write_canonical_annotation_set(annotation_set)
        return {"annotation_set": annotation_set.to_dict(), "review": review.to_dict()}

    def prepare_xanylabeling_project(
        self,
        dataset_id: str,
        schema_id: str,
        output_dir: str,
        asset_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        self._require_dataset(dataset_id)
        schema = self._require_schema(schema_id)
        assets = self.workspace.metadata.list_assets(dataset_id)
        if asset_ids is not None:
            wanted = set(asset_ids)
            assets = [asset for asset in assets if asset.id in wanted]
        result = XAnyLabelingProjectAdapter().prepare_project(dataset_id, schema, assets, Path(output_dir))
        return result.to_dict()

    def prepare_labeling_project(
        self,
        tool: str,
        dataset_id: str,
        schema_id: str,
        output_dir: str,
        asset_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        self._require_dataset(dataset_id)
        schema = self._require_schema(schema_id)
        assets = self.workspace.metadata.list_assets(dataset_id)
        if asset_ids is not None:
            wanted = set(asset_ids)
            assets = [asset for asset in assets if asset.id in wanted]
        normalized = _normalize_tool(tool)
        if normalized in {"x-anylabeling", "labelme"}:
            result = XAnyLabelingProjectAdapter().prepare_project(dataset_id, schema, assets, Path(output_dir))
        elif normalized == "isat":
            result = prepare_isat_project(dataset_id, schema, assets, Path(output_dir))
        else:
            raise ValueError(f"Unsupported labeling tool: {tool}")
        return result.to_dict()

    def detect_xanylabeling(self) -> dict[str, Any]:
        return detect_xanylabeling().to_dict()

    def launch_xanylabeling_project(self, project_dir: str) -> dict[str, Any]:
        return launch_xanylabeling_project(project_dir)

    def detect_labeling_tool(self, tool: str) -> dict[str, Any]:
        return detect_labeling_tool(tool).to_dict()

    def launch_labeling_project(self, tool: str, project_dir: str) -> dict[str, Any]:
        return launch_labeling_project(tool, project_dir)

    def import_xanylabeling_annotations(
        self,
        dataset_id: str,
        schema_id: str,
        asset_id: str,
        input_path: str,
    ) -> dict[str, Any]:
        return self.import_annotations(dataset_id, schema_id, "x-anylabeling", input_path, asset_id=asset_id)

    def import_xanylabeling_project_labels(
        self,
        dataset_id: str,
        schema_id: str,
        labels_dir: str,
    ) -> dict[str, Any]:
        """Import all LabelMe JSON files from an X-AnyLabeling labels/ directory.

        Matches each JSON to an asset automatically using the imagePath field.
        Returns the merged AnnotationSet, an aggregated conversion report, and
        a list of JSON filenames that could not be matched to any dataset asset.
        """
        return self.import_project_labels(dataset_id, schema_id, "x-anylabeling", labels_dir)

    def import_annotations(
        self,
        dataset_id: str,
        schema_id: str,
        input_format: str,
        input_path: str,
        asset_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_dataset(dataset_id)
        schema = self._require_schema(schema_id)
        fmt = _normalize_format(input_format)
        if fmt == "coco":
            asset = None
        elif asset_id is None:
            asset = self._asset_for_annotation_file(dataset_id, input_path, fmt)
        else:
            asset = self._require_asset(dataset_id, asset_id)
        if fmt in {"labelme", "x-anylabeling"}:
            annotation_set, report = import_labelme_file(input_path, dataset_id, schema, asset)
        elif fmt == "isat":
            annotation_set, report = import_isat_file(input_path, dataset_id, schema, asset)
        elif fmt == "coco":
            assets = self.workspace.metadata.list_assets(dataset_id)
            annotation_set, report, _unmatched = import_coco_file(input_path, dataset_id, schema, assets)
        else:
            raise ValueError(f"Unsupported import format: {input_format}")
        self.workspace.write_canonical_annotation_set(annotation_set)
        return {"annotation_set": annotation_set.to_dict(), "conversion_report": report.to_dict()}

    def import_project_labels(
        self,
        dataset_id: str,
        schema_id: str,
        input_format: str,
        labels_dir: str,
    ) -> dict[str, Any]:
        self._require_dataset(dataset_id)
        schema = self._require_schema(schema_id)
        assets = self.workspace.metadata.list_assets(dataset_id)
        fmt = _normalize_format(input_format)
        if fmt in {"labelme", "x-anylabeling"}:
            annotation_set, report, unmatched = import_labelme_project_dir(
                Path(labels_dir), dataset_id, schema, assets
            )
        elif fmt == "isat":
            annotation_set, report, unmatched = import_isat_project_dir(
                Path(labels_dir), dataset_id, schema, assets
            )
        elif fmt == "yolo-detection":
            annotation_set, report, unmatched = import_yolo_detection_dir(
                Path(labels_dir), dataset_id, schema, assets
            )
        elif fmt == "yolo-segmentation":
            annotation_set, report, unmatched = import_yolo_segmentation_dir(
                Path(labels_dir), dataset_id, schema, assets
            )
        else:
            raise ValueError(f"Unsupported import format: {input_format}")
        self.workspace.write_canonical_annotation_set(annotation_set)
        return {
            "annotation_set": annotation_set.to_dict(),
            "conversion_report": report.to_dict(),
            "unmatched_files": unmatched,
            "matched_count": len(annotation_set.annotations),
        }

    def supported_annotation_formats(self) -> list[dict[str, Any]]:
        return [
            {"id": "labelme", "name": "LabelMe JSON", "can_import": True, "can_export": True},
            {"id": "x-anylabeling", "name": "X-AnyLabeling JSON", "can_import": True, "can_export": True},
            {"id": "isat", "name": "ISAT JSON", "can_import": True, "can_export": True},
            {"id": "coco", "name": "COCO", "can_import": True, "can_export": True},
            {"id": "yolo-detection", "name": "YOLO Detection", "can_import": True, "can_export": True},
            {"id": "yolo-segmentation", "name": "YOLO Segmentation", "can_import": True, "can_export": True},
        ]

    def create_export(
        self,
        annotation_set_id: str,
        export_format: str,
        output_dir: str,
        purpose: str = "preview",
    ) -> dict[str, Any]:
        annotation_set = self._require_annotation_set(annotation_set_id)
        if purpose in {"training", "publish"} and annotation_set.state != "approved":
            raise ConflictError(
                "Training or publish exports require an approved annotation set.",
                {"annotation_set_id": annotation_set.id, "state": annotation_set.state, "purpose": purpose},
            )
        schema = self._require_schema(annotation_set.schema_id)
        assets = {asset.id: asset for asset in self.workspace.metadata.list_assets(annotation_set.dataset_id)}
        output = Path(output_dir)
        result: AdapterResult
        normalized_format = _normalize_format(export_format)
        if normalized_format in {"labelme", "x-anylabeling"}:
            result = export_labelme(annotation_set, schema, assets, output)
        elif normalized_format == "isat":
            result = export_isat(annotation_set, schema, assets, output)
        elif normalized_format == "coco":
            result = export_coco(annotation_set, schema, assets, output)
        elif normalized_format == "yolo-detection":
            result = export_yolo_detection(annotation_set, schema, assets, output)
        elif normalized_format == "yolo-segmentation":
            result = export_yolo_segmentation(annotation_set, schema, assets, output)
        else:
            raise ValueError(f"Unsupported export format: {export_format}")
        payload = result.to_dict()
        export_id = new_id("export")
        payload["export_id"] = export_id
        payload["annotation_set_id"] = annotation_set.id
        payload["purpose"] = purpose
        payload["format"] = export_format
        self.workspace.metadata.save_export(export_id, annotation_set.id, payload)
        return payload

    def get_export(self, export_id: str) -> dict[str, Any]:
        export_record = self.workspace.metadata.get_export(export_id)
        if export_record is None:
            raise NotFoundError("export", export_id)
        return export_record

    def _asset_for_annotation_file(self, dataset_id: str, input_path: str, input_format: str):
        path = Path(input_path)
        assets = self.workspace.metadata.list_assets(dataset_id)
        by_filename = {Path(asset.uri).name: asset for asset in assets}
        try:
            import json

            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if input_format == "isat":
            image_name = Path(payload.get("info", {}).get("name", "")).name
        else:
            image_name = Path(payload.get("imagePath", "")).name
        if image_name and image_name in by_filename:
            return by_filename[image_name]
        if len(assets) == 1:
            return assets[0]
        raise NotFoundError("asset", image_name or path.stem)

    def _require_dataset(self, dataset_id: str):
        dataset = self.workspace.metadata.get_dataset(dataset_id)
        if dataset is None:
            raise NotFoundError("dataset", dataset_id)
        return dataset

    def _require_schema(self, schema_id: str) -> LabelSchema:
        schema = self.workspace.metadata.get_schema(schema_id)
        if schema is None:
            raise NotFoundError("schema", schema_id)
        return schema

    def _require_annotation_set(self, annotation_set_id: str) -> AnnotationSet:
        annotation_set = self.workspace.metadata.get_annotation_set(annotation_set_id)
        if annotation_set is None:
            raise NotFoundError("annotation_set", annotation_set_id)
        return annotation_set

    def _require_asset(self, dataset_id: str, asset_id: str):
        for asset in self.workspace.metadata.list_assets(dataset_id):
            if asset.id == asset_id:
                return asset
        raise NotFoundError("asset", asset_id)


def _annotation_from_payload(payload: dict[str, Any]) -> Annotation:
    data = dict(payload)
    geometry_data = data.pop("geometry", None)
    geometry = None
    if geometry_data:
        geometry_type = geometry_data.get("type")
        if geometry_type == "bbox":
            geometry = BBoxGeometry.from_dict(geometry_data)
        elif geometry_type == "polygon":
            geometry = PolygonGeometry.from_dict(geometry_data)
        else:
            raise ValueError(f"Unsupported geometry type: {geometry_type}")
    classification_data = data.pop("classification", None)
    classification = None
    if classification_data:
        classification = [ClassificationValue.from_dict(item) for item in classification_data]
    return Annotation(
        asset_id=data["asset_id"],
        label_id=data.get("label_id"),
        geometry=geometry,
        classification=classification,
        id=data.get("id") or new_id("ann"),
        confidence=data.get("confidence"),
        source=data.get("source", "human"),
        attributes=data.get("attributes", {}),
        review_status=data.get("review_status", "draft"),
        provenance=data.get("provenance", {}),
        version=data.get("version", 1),
    )


def _normalize_format(value: str) -> str:
    fmt = (value or "").strip().lower().replace("_", "-")
    aliases = {
        "xanylabeling": "x-anylabeling",
        "x-any": "x-anylabeling",
        "yolo": "yolo-detection",
        "yolo-detect": "yolo-detection",
        "yolo-detection": "yolo-detection",
        "yolo-seg": "yolo-segmentation",
        "yolo-segment": "yolo-segmentation",
        "yolo-segmentation": "yolo-segmentation",
        "yolo-segmentations": "yolo-segmentation",
    }
    return aliases.get(fmt, fmt)


def _normalize_tool(value: str) -> str:
    tool = (value or "").strip().lower().replace("_", "-")
    if tool == "xanylabeling":
        return "x-anylabeling"
    return tool
