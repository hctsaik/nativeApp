from __future__ import annotations

import base64
import json
from typing import Any, Callable

from plugins.labeling.domain.core.errors import AnnotationError
from plugins.labeling.domain.services import AnnotationService


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

    # ── Phase 0: Tenant 管理 ──────────────────────────────────────────────────

    def register_tenant(
        self,
        system_name: str,
        server_host_name: str,
        target_format: str,
        api_token: str | None = None,
    ) -> str:
        return call_service(
            lambda: self.service.register_tenant(system_name, server_host_name, target_format, api_token)
        )

    def list_tenants(self) -> str:
        return call_service(self.service.list_tenants)

    def get_tenant(self, tenant_id: str) -> str:
        return call_service(lambda: self.service.get_tenant(tenant_id))

    def add_user_to_tenant(self, tenant_id: str, user_id: str) -> str:
        return call_service(lambda: self.service.add_user_to_tenant(tenant_id, user_id))

    def list_tenant_users(self, tenant_id: str) -> str:
        return call_service(lambda: self.service.list_tenant_users(tenant_id))

    # ── Phase 1: 任務發現 ─────────────────────────────────────────────────────

    def get_ant_list(self, tenant_id: str) -> str:
        return call_service(lambda: self.service.get_ant_list(tenant_id))

    # ── Phase 2: 任務認領 + 標注更新 ─────────────────────────────────────────

    def claim_task(self, tenant_id: str, ant_id: str, user_id: str) -> str:
        return call_service(lambda: self.service.claim_task(tenant_id, ant_id, user_id))

    def save_annotation(
        self,
        task_id: str,
        annotation_json_str: str,
        new_classification: str | None = None,
        annotated_by: str | None = None,
    ) -> str:
        return call_service(
            lambda: self.service.save_annotation(
                task_id,
                _loads_object(annotation_json_str),
                new_classification,
                annotated_by,
            )
        )

    def complete_task(self, task_id: str, annotated_by: str) -> str:
        return call_service(lambda: self.service.complete_task(task_id, annotated_by))

    def get_task(self, task_id: str) -> str:
        return call_service(lambda: self.service.get_task(task_id))

    def list_tasks(
        self,
        tenant_id: str,
        user_id: str | None = None,
        ant_active: int | None = None,
    ) -> str:
        return call_service(lambda: self.service.list_tasks(tenant_id, user_id, ant_active))

    # ── Phase 3: CIM Sponsor 下載 ─────────────────────────────────────────────

    def get_dashboard_stats(self, tenant_id: str) -> str:
        return call_service(lambda: self.service.get_dashboard_stats(tenant_id))

    def export_result_zip(self, task_id: str, mode: str) -> str:
        """回傳 base64 編碼的 ZIP bytes。"""
        def _export():
            raw = self.service.export_result_zip(task_id, mode)
            return {"zip_b64": base64.b64encode(raw).decode("ascii"), "size_bytes": len(raw)}
        return call_service(_export)

    # ── 舊版 FormatRegistry / dry-run / tool 相關 handler（保留以維持向後相容） ──

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

    def review_task_legacy(self, annotation_set_id: str, decision: str, actor_id: str, comment: str = "") -> str:
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

    def prepare_labeling_project(
        self,
        tool: str,
        dataset_id: str,
        schema_id: str,
        output_dir: str,
        asset_ids_json: str = "null",
    ) -> str:
        asset_ids = json.loads(asset_ids_json)
        return call_service(
            lambda: self.service.prepare_labeling_project(tool, dataset_id, schema_id, output_dir, asset_ids)
        )

    def detect_xanylabeling(self) -> str:
        return call_service(self.service.detect_xanylabeling)

    def launch_xanylabeling_project(self, project_dir: str) -> str:
        return call_service(lambda: self.service.launch_xanylabeling_project(project_dir))

    def detect_labeling_tool(self, tool: str) -> str:
        return call_service(lambda: self.service.detect_labeling_tool(tool))

    def launch_labeling_project(self, tool: str, project_dir: str) -> str:
        return call_service(lambda: self.service.launch_labeling_project(tool, project_dir))

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

    def import_annotations(
        self,
        dataset_id: str,
        schema_id: str,
        input_format: str,
        input_path: str,
        asset_id: str | None = None,
    ) -> str:
        return call_service(
            lambda: self.service.import_annotations(dataset_id, schema_id, input_format, input_path, asset_id)
        )

    def import_project_labels(
        self,
        dataset_id: str,
        schema_id: str,
        input_format: str,
        labels_dir: str,
    ) -> str:
        return call_service(
            lambda: self.service.import_project_labels(dataset_id, schema_id, input_format, labels_dir)
        )

    def supported_annotation_formats(self) -> str:
        return call_service(self.service.supported_annotation_formats)

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

    def dry_run_export(
        self,
        annotation_set_id: str,
        export_format: str,
        options_json: str = "{}",
    ) -> str:
        return call_service(
            lambda: self.service.dry_run_export(
                annotation_set_id, export_format, _loads_object(options_json)
            )
        )

    def list_labeling_tools(self) -> str:
        return call_service(self.service.list_labeling_tools)

    def get_job_status(self, job_id: str) -> str:
        return call_service(lambda: self.service.get_job_status(job_id))

    def cancel_job(self, job_id: str) -> str:
        return call_service(lambda: self.service.cancel_job(job_id))


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
