from __future__ import annotations

import json
from typing import Any, Callable

from annotation.core.errors import AnnotationError
from annotation.services import AnnotationService


def ok(payload: Any) -> str:
    return json.dumps({"ok": True, "data": payload}, ensure_ascii=False, indent=2)


def fail(exc: Exception) -> str:
    if isinstance(exc, AnnotationError):
        return json.dumps(exc.to_dict(), ensure_ascii=False, indent=2)
    return json.dumps(
        {
            "ok": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": str(exc),
                "details": {},
                "retryable": False,
            },
        },
        ensure_ascii=False,
        indent=2,
    )


def call_service(callback: Callable[[], Any]) -> str:
    try:
        return ok(callback())
    except Exception as exc:
        return fail(exc)


class AnnotationMCPHandlers:
    def __init__(self, service: AnnotationService) -> None:
        self.service = service

    def create_dataset(self, name: str, root_uri: str, metadata_json: str = "{}") -> str:
        return call_service(
            lambda: self.service.create_dataset(name, root_uri, _loads_object(metadata_json))
        )

    def list_datasets(self) -> str:
        return call_service(self.service.list_datasets)

    def ingest_assets(self, dataset_id: str, image_paths_json: str, copy: bool = True) -> str:
        return call_service(
            lambda: self.service.ingest_assets(dataset_id, _loads_list(image_paths_json), copy)
        )

    def create_schema(
        self,
        name: str,
        labels_json: str,
        attribute_schema_json: str = "[]",
        version: str = "1.0",
        schema_id: str | None = None,
    ) -> str:
        return call_service(
            lambda: self.service.create_schema(
                name=name,
                labels=_loads_list(labels_json),
                attribute_schema=_loads_list(attribute_schema_json),
                version=version,
                schema_id=schema_id,
            )
        )

    def get_schema(self, schema_id: str) -> str:
        return call_service(lambda: self.service.get_schema(schema_id))

    def create_annotation_set(
        self,
        dataset_id: str,
        schema_id: str,
        annotations_json: str = "[]",
        source: str = "human",
        created_by: str | None = None,
    ) -> str:
        return call_service(
            lambda: self.service.create_annotation_set(
                dataset_id,
                schema_id,
                _loads_list(annotations_json),
                source,
                created_by,
            )
        )

    def get_asset_annotations(self, annotation_set_id: str, asset_id: str | None = None) -> str:
        return call_service(lambda: self.service.get_asset_annotations(annotation_set_id, asset_id))

    def get_task(self, task_id: str) -> str:
        return call_service(lambda: self.service.get_task(task_id))

    def list_tasks(self, dataset_id: str | None = None) -> str:
        return call_service(lambda: self.service.list_tasks(dataset_id))

    def upsert_annotations(
        self,
        annotation_set_id: str,
        annotations_json: str,
        base_version: int | None = None,
        replace: bool = True,
    ) -> str:
        return call_service(
            lambda: self.service.upsert_annotations(
                annotation_set_id,
                _loads_list(annotations_json),
                base_version,
                replace,
            )
        )

    def validate_set(self, annotation_set_id: str) -> str:
        return call_service(lambda: self.service.validate_set(annotation_set_id))

    def submit_for_review(self, annotation_set_id: str) -> str:
        return call_service(lambda: self.service.submit_for_review(annotation_set_id))

    def review_task(self, annotation_set_id: str, decision: str, actor_id: str, comment: str = "") -> str:
        return call_service(lambda: self.service.review_task(annotation_set_id, decision, actor_id, comment))

    def prepare_xanylabeling_project(
        self,
        dataset_id: str,
        schema_id: str,
        output_dir: str,
        asset_ids_json: str = "null",
    ) -> str:
        asset_ids = json.loads(asset_ids_json)
        return call_service(
            lambda: self.service.prepare_xanylabeling_project(dataset_id, schema_id, output_dir, asset_ids)
        )

    def detect_xanylabeling(self) -> str:
        return call_service(self.service.detect_xanylabeling)

    def launch_xanylabeling_project(self, project_dir: str) -> str:
        return call_service(lambda: self.service.launch_xanylabeling_project(project_dir))

    def import_xanylabeling(
        self,
        dataset_id: str,
        schema_id: str,
        asset_id: str,
        input_path: str,
    ) -> str:
        return call_service(
            lambda: self.service.import_xanylabeling_annotations(dataset_id, schema_id, asset_id, input_path)
        )

    def import_xanylabeling_project_labels(
        self,
        dataset_id: str,
        schema_id: str,
        labels_dir: str,
    ) -> str:
        return call_service(
            lambda: self.service.import_xanylabeling_project_labels(dataset_id, schema_id, labels_dir)
        )

    def create_export(
        self,
        annotation_set_id: str,
        export_format: str,
        output_dir: str,
        purpose: str = "preview",
    ) -> str:
        return call_service(
            lambda: self.service.create_export(annotation_set_id, export_format, output_dir, purpose)
        )

    def get_export(self, export_id: str) -> str:
        return call_service(lambda: self.service.get_export(export_id))

    def get_job_status(self, job_id: str) -> str:
        return ok({"job_id": job_id, "state": "succeeded", "message": "MVP operations run synchronously."})

    def cancel_job(self, job_id: str) -> str:
        return ok({"job_id": job_id, "state": "not_cancelable", "message": "MVP operations run synchronously."})


def _loads_object(value: str) -> dict[str, Any]:
    data = json.loads(value)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object.")
    return data


def _loads_list(value: str) -> list[Any]:
    data = json.loads(value)
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array.")
    return data
