from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen
from uuid import uuid4

from plugins.labeling.domain.adapters.labeling_runtime import detect_labeling_tool, launch_labeling_project
from plugins.labeling.domain.adapters.xanylabeling import XAnyLabelingProjectAdapter
from plugins.labeling.domain.adapters.xanylabeling_runtime import detect_xanylabeling, launch_xanylabeling_project
from plugins.labeling.domain.core.errors import ConflictError, NotFoundError, ValidationFailedError
from plugins.labeling.domain.core.models import (
    AdapterResult,
    Annotation,
    AnnotationSet,
    AnnotationTask,
    AttributeDef,
    BBoxGeometry,
    ClassificationValue,
    LabelDef,
    LabelSchema,
    SystemTenant,
    TenantUserMapping,
    new_id,
    utc_now_iso,
)
from plugins.labeling.domain.core.states import apply_review_decision, transition_annotation_set
from plugins.labeling.domain.core.validation import validate_annotation_set
from plugins.labeling.domain.formats.registry import get_format_registry
from core.integrations.connector import ExternalSystemConnector
from plugins.labeling.domain.storage.workspace import AnnotationWorkspace
from plugins.labeling.domain.tools.registry import get_tool_registry


def _new_uuid() -> str:
    return str(uuid4())


class AnnotationService:
    def __init__(self, workspace: AnnotationWorkspace) -> None:
        self.workspace = workspace

    # ── Phase 0: Tenant 管理 ──────────────────────────────────────────────────

    def register_tenant(
        self,
        system_name: str,
        server_host_name: str,
        target_format: str,
        api_token: str | None = None,
        connector_type: str | None = None,
        connector_config: dict | None = None,
    ) -> dict[str, Any]:
        tenant = SystemTenant(
            tenant_id=_new_uuid(),
            system_name=system_name,
            server_host_name=server_host_name.rstrip("/"),
            target_format=target_format,
            api_token=api_token,
            created_at=utc_now_iso(),
            connector_type=connector_type,
            connector_config=connector_config,
        )
        self.workspace.metadata.save_tenant(tenant)
        return _tenant_to_dict(tenant)

    def list_tenants(self) -> list[dict[str, Any]]:
        return [_tenant_to_dict(t) for t in self.workspace.metadata.list_tenants()]

    def sync_external_systems(self, declared: list[dict]) -> list[str]:
        """Idempotently register declared external systems (no-code via YAML).

        `declared` is a list of {system_name, server_host_name, target_format,
        api_token? | api_token_env?}. Matches existing tenants by
        (system_name, server_host_name) so re-syncing never duplicates. Tokens
        are read from the named env var (`api_token_env`) — never stored in the
        YAML. Returns the names of newly-registered systems.
        """
        import os  # noqa: PLC0415
        existing = {(t["system_name"], (t["server_host_name"] or "").rstrip("/"))
                    for t in self.list_tenants()}
        registered: list[str] = []
        for sysd in declared or []:
            name = sysd.get("system_name")
            host = (sysd.get("server_host_name") or "").rstrip("/")
            fmt = sysd.get("target_format")
            if not (name and host and fmt) or (name, host) in existing:
                continue
            token = sysd.get("api_token") or (
                os.environ.get(sysd["api_token_env"]) if sysd.get("api_token_env") else None)
            self.register_tenant(name, host, fmt, api_token=token,
                                 connector_type=sysd.get("connector_type"),
                                 connector_config=sysd.get("rest_mapping")
                                 or sysd.get("connector_config"))
            registered.append(name)
            existing.add((name, host))
        return registered

    def get_tenant(self, tenant_id: str) -> dict[str, Any]:
        tenant = self._require_tenant(tenant_id)
        return _tenant_to_dict(tenant)

    def delete_tenant(self, tenant_id: str) -> None:
        self._require_tenant(tenant_id)
        self.workspace.metadata.delete_tenant(tenant_id)

    def add_user_to_tenant(self, tenant_id: str, user_id: str, ant_id: str | None = None) -> dict[str, Any]:
        self._require_tenant(tenant_id)
        mapping = TenantUserMapping(
            id=_new_uuid(),
            tenant_id=tenant_id,
            user_id=user_id,
            ant_id=ant_id,
        )
        self.workspace.metadata.add_user_mapping(mapping)
        return {"id": mapping.id, "tenant_id": tenant_id, "user_id": user_id, "ant_id": ant_id}

    def list_tenant_users(self, tenant_id: str, ant_id: str | None = None) -> list[dict[str, Any]]:
        self._require_tenant(tenant_id)
        return [
            {"id": m.id, "tenant_id": m.tenant_id, "user_id": m.user_id, "ant_id": m.ant_id}
            for m in self.workspace.metadata.list_user_mappings(tenant_id, ant_id=ant_id)
        ]

    def remove_user_from_tenant(self, tenant_id: str, user_id: str, ant_id: str | None = None) -> None:
        self._require_tenant(tenant_id)
        self.workspace.metadata.remove_user_mapping(tenant_id, user_id, ant_id=ant_id)

    def get_task_restriction_map(self, tenant_id: str) -> dict[str, list[str]]:
        """回傳 {ant_id: [user_id, ...]} — 僅包含有 per-task 限制的任務。"""
        self._require_tenant(tenant_id)
        result: dict[str, list[str]] = {}
        for m in self.workspace.metadata.list_all_user_mappings(tenant_id):
            if m.ant_id is not None:
                result.setdefault(m.ant_id, []).append(m.user_id)
        return result

    # ── Phase 1: 任務發現（不存 DB，直接呼叫 connector） ────────────────────

    def get_ant_list(self, tenant_id: str) -> list[dict[str, Any]]:
        tenant = self._require_tenant(tenant_id)
        connector = self._get_connector(tenant)
        tasks = connector.get_ant_list()
        return [
            {
                "ant_id": t.ant_id,
                "ant_active": t.ant_active,
                "ant_period": t.ant_period,
                "external_context": t.external_context,
            }
            for t in tasks
        ]

    # ── Phase 2: 任務認領 + ZIP 下載入庫 ────────────────────────────────────

    def claim_task(self, tenant_id: str, ant_id: str, user_id: str) -> dict[str, Any]:
        """
        認領外部系統任務：
        1. 取得 connector → get_ant_task_detail → download_url
        2. 下載 ZIP → 解壓到 workspace
        3. 用 FormatRegistry 解析標注
        4. 建立 AnnotationTask(ant_active=1) 存 DB
        """
        tenant = self._require_tenant(tenant_id)

        # 授權檢查：若任務有設定 per-task 白名單，則驗證 user_id
        task_users = self.workspace.metadata.list_user_mappings(tenant_id, ant_id=ant_id)
        if task_users:
            allowed = {m.user_id for m in task_users}
            if user_id not in allowed:
                raise PermissionError(
                    f"使用者 {user_id} 未獲授權認領任務 {ant_id}。"
                    f"（已授權：{', '.join(sorted(allowed))}）"
                )

        # 防重複認領
        existing = self.workspace.metadata.get_task_by_ant_id(tenant_id, ant_id)
        if existing is not None:
            return _task_to_dict(existing)

        connector = self._get_connector(tenant)

        # 通知外部系統認領（best-effort：連線失敗不阻斷流程）
        try:
            connector.mark_task_claimed(ant_id)
        except RuntimeError as exc:
            if "已被他人認領" in str(exc):
                raise ConflictError(f"此任務已被他人認領（ant_id={ant_id}）") from exc
            raise
        except ConnectionRefusedError:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "mark_task_claimed 連線失敗，跳過回寫（ant_id=%s）", ant_id
            )

        detail = connector.get_ant_task_detail(ant_id, tenant.target_format)
        download_url = detail.download_url

        task_id = _new_uuid()
        images_dir = self.workspace.ensure_task_images_dir(task_id)
        annotation_json: dict[str, Any] = {}

        if download_url:
            # 下載並解壓 ZIP
            zip_bytes = _download_bytes(download_url)

            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                names = zf.namelist()
                # 解壓 images/
                for name in names:
                    if name.startswith("images/") and not name.endswith("/"):
                        img_data = zf.read(name)
                        dest = images_dir / Path(name).name
                        dest.write_bytes(img_data)

                # 解析標注檔（嘗試用 FormatRegistry）
                annotation_json = _parse_annotations_from_zip(zf, names, tenant.target_format, task_id, images_dir)

        now = utc_now_iso()
        task = AnnotationTask(
            task_id=task_id,
            tenant_id=tenant_id,
            ant_id=ant_id,
            ant_active=1,
            annotation_json=annotation_json,
            original_annotation_json=annotation_json,
            external_context={},
            annotated_by=user_id,
            created_at=now,
            updated_at=now,
        )
        # 原子認領：DB 對 (tenant_id, ant_id) 有 UNIQUE 約束；本地併發競態下
        # 第二位認領者會撞 UNIQUE → 翻成 ConflictError（與外部回寫衝突同一語意，
        # guidance 會顯示「任務已被認領」引導卡）。
        try:
            self.workspace.metadata.save_task(task)
        except Exception as exc:  # noqa: BLE001
            if "unique" in str(exc).lower() and "ant_id" in str(exc).lower():
                existing = self.workspace.metadata.get_task_by_ant_id(tenant_id, ant_id)
                if existing is not None:
                    return _task_to_dict(existing)
                raise ConflictError(f"此任務已被他人認領（ant_id={ant_id}）") from exc
            raise
        return _task_to_dict(task)

    def save_annotation(
        self,
        task_id: str,
        annotation_json: dict[str, Any],
        new_classification: str | None = None,
        annotated_by: str | None = None,
    ) -> dict[str, Any]:
        task = self._require_task(task_id)
        task.annotation_json = annotation_json
        if new_classification is not None:
            task.new_classification = new_classification
        if annotated_by is not None:
            task.annotated_by = annotated_by
        task.updated_at = utc_now_iso()
        self.workspace.metadata.save_task(task)
        return _task_to_dict(task)

    def complete_task(self, task_id: str, annotated_by: str) -> dict[str, Any]:
        task = self._require_task(task_id)
        task.ant_active = 2
        task.annotated_by = annotated_by
        task.updated_at = utc_now_iso()
        self.workspace.metadata.save_task(task)

        # deliver result back to external system
        tenant = self._require_tenant(task.tenant_id)
        connector = self._get_connector(tenant)
        try:
            delivery = connector.deliver_result(
                ant_id=task.ant_id,
                platform_task_id=task_id,
                annotation_json=task.annotation_json or {},
                new_classification=task.new_classification,
                annotated_by=task.annotated_by,
            )
        except Exception as exc:
            delivery = {"status": "error", "error": str(exc)}
        # store delivery result in task record
        self.workspace.update_task_delivery(task_id, delivery)
        task = self._require_task(task_id)  # reload so delivery_status is current

        return {**_task_to_dict(task), "delivery": delivery}

    def get_task(self, task_id: str) -> dict[str, Any]:
        return _task_to_dict(self._require_task(task_id))

    def list_tasks(
        self,
        tenant_id: str,
        user_id: str | None = None,
        ant_active: int | None = None,
    ) -> list[dict[str, Any]]:
        self._require_tenant(tenant_id)
        tasks = self.workspace.metadata.list_tasks(tenant_id, ant_active)
        if user_id is not None:
            tasks = [t for t in tasks if t.annotated_by == user_id]
        return [_task_to_dict(t) for t in tasks]

    # ── Phase 3: CIM Sponsor 下載 ─────────────────────────────────────────────

    def get_dashboard_stats(self, tenant_id: str) -> dict[str, Any]:
        self._require_tenant(tenant_id)
        all_tasks = self.workspace.metadata.list_tasks(tenant_id)
        counts = {0: 0, 1: 0, 2: 0}
        for t in all_tasks:
            counts[t.ant_active] = counts.get(t.ant_active, 0) + 1
        return {
            "tenant_id": tenant_id,
            "pending": counts[0],
            "processing": counts[1],
            "completed": counts[2],
            "total": len(all_tasks),
        }

    def export_result_zip(self, task_id: str, mode: str) -> bytes:
        """
        打包結果 ZIP，回傳 bytes。
        mode: "orig_img_orig_ant" | "orig_img_new_ant"
        ZIP 結構: images/ + annotations.<ext> + annotated_by.txt
        """
        task = self._require_task(task_id)
        if mode not in {"orig_img_orig_ant", "orig_img_new_ant"}:
            raise ValueError(f"不支援的 export mode: {mode!r}")

        images_dir = self.workspace.task_images_dir(task_id)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # 寫入 images/
            if images_dir.exists():
                for img_file in sorted(images_dir.iterdir()):
                    if img_file.is_file():
                        zf.writestr(f"images/{img_file.name}", img_file.read_bytes())

            # 決定標注內容
            if mode == "orig_img_orig_ant":
                ant_data = task.original_annotation_json
            else:
                # new_ant：annotation_json 為最新標注結果（annotator 已更新）
                ant_data = task.annotation_json

            # 寫入標注檔
            zf.writestr("annotations.json", json.dumps(ant_data, ensure_ascii=False, indent=2))

            # 寫入 annotated_by
            zf.writestr(
                "annotated_by.txt",
                task.annotated_by or "",
            )

        return buf.getvalue()

    # ── Connector 取得 ────────────────────────────────────────────────────────

    def _get_connector(self, tenant: SystemTenant) -> ExternalSystemConnector:
        # 宣告式選型：tenant.connector_type 優先，否則依 server_host_name scheme 推斷。
        # 新協定只需 register_connector("...", factory)，不必改這裡。
        from plugins.labeling.domain.integrations.registry import build_connector
        return build_connector(tenant)

    # ── 舊版 API（FormatRegistry / dry-run 相容） ─────────────────────────────

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
            annotations = [a for a in annotations if a.asset_id == asset_id]
        return {
            "annotation_set_id": annotation_set.id,
            "annotations": [a.to_dict() for a in annotations],
        }

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
            by_id = {a.id: a for a in annotation_set.annotations}
            for a in incoming:
                by_id[a.id] = a
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
            assets = [a for a in assets if a.id in wanted]
        result = XAnyLabelingProjectAdapter().prepare_project(dataset_id, schema, assets, Path(output_dir))
        return result.to_dict()

    def detect_xanylabeling(self) -> dict[str, Any]:
        return detect_xanylabeling().to_dict()

    def launch_xanylabeling_project(self, project_dir: str) -> dict[str, Any]:
        return launch_xanylabeling_project(project_dir)

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
        return self.import_project_labels(dataset_id, schema_id, "x-anylabeling", labels_dir)

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
            assets = [a for a in assets if a.id in wanted]
        canonical = get_tool_registry().normalize(tool)
        if canonical == "isat":
            from plugins.labeling.domain.adapters.isat import prepare_isat_project
            result = prepare_isat_project(dataset_id, schema, assets, Path(output_dir))
        else:
            result = XAnyLabelingProjectAdapter().prepare_project(dataset_id, schema, assets, Path(output_dir))
        return result.to_dict()

    def detect_labeling_tool(self, tool: str) -> dict[str, Any]:
        registry = get_tool_registry()
        try:
            _, adapter = registry.get(tool)
            return adapter.detect().to_dict()
        except ValueError:
            return detect_labeling_tool(tool).to_dict()

    def launch_labeling_project(self, tool: str, project_dir: str) -> dict[str, Any]:
        registry = get_tool_registry()
        try:
            desc, adapter = registry.get(tool)
            return adapter.launch_project(Path(project_dir), {})
        except ValueError:
            return launch_labeling_project(tool, project_dir)

    def list_labeling_tools(self) -> list[dict[str, Any]]:
        return get_tool_registry().list_supported()

    def supported_annotation_formats(self) -> list[dict[str, Any]]:
        return get_format_registry().list_supported()

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
        registry = get_format_registry()
        fmt = registry.normalize(input_format)
        desc, adapter = registry.get(fmt)
        all_assets = self.workspace.metadata.list_assets(dataset_id)

        if not desc.capabilities.requires_asset:
            asset = None
        elif asset_id is not None:
            asset = self._require_asset(dataset_id, asset_id)
        else:
            asset = self._asset_for_annotation_file(dataset_id, input_path, fmt)

        annotation_set, report = adapter.import_file(input_path, dataset_id, schema, asset, all_assets)
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
        registry = get_format_registry()
        desc, adapter = registry.get(input_format)
        annotation_set, report, unmatched = adapter.import_dir(Path(labels_dir), dataset_id, schema, assets)
        self.workspace.write_canonical_annotation_set(annotation_set)
        return {
            "annotation_set": annotation_set.to_dict(),
            "conversion_report": report.to_dict(),
            "unmatched_files": unmatched,
            "matched_count": len(annotation_set.annotations),
        }

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
        _, adapter = get_format_registry().get(export_format)
        result = adapter.export(annotation_set, schema, assets, Path(output_dir))
        payload = result.to_dict()
        export_id = new_id("export")
        payload["export_id"] = export_id
        payload["annotation_set_id"] = annotation_set.id
        payload["purpose"] = purpose
        payload["format"] = export_format
        self.workspace.metadata.save_export(export_id, annotation_set.id, payload)
        return payload

    def dry_run_export(
        self,
        annotation_set_id: str,
        export_format: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        annotation_set = self._require_annotation_set(annotation_set_id)
        schema = self._require_schema(annotation_set.schema_id)
        assets = {asset.id: asset for asset in self.workspace.metadata.list_assets(annotation_set.dataset_id)}
        _, adapter = get_format_registry().get(export_format)
        result = adapter.export(annotation_set, schema, assets, Path("."), dry_run=True)
        return result.conversion_report.to_dict()

    def get_export(self, export_id: str) -> dict[str, Any]:
        export_record = self.workspace.metadata.get_export(export_id)
        if export_record is None:
            raise NotFoundError("export", export_id)
        return export_record

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        return {"job_id": job_id, "state": "succeeded", "message": "MVP operations run synchronously."}

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        return {"job_id": job_id, "state": "not_cancelable", "message": "MVP: no async jobs to cancel."}

    # ── Private helpers ───────────────────────────────────────────────────────

    def _require_tenant(self, tenant_id: str) -> SystemTenant:
        tenant = self.workspace.metadata.get_tenant(tenant_id)
        if tenant is None:
            raise NotFoundError("tenant", tenant_id)
        return tenant

    def _require_task(self, task_id: str) -> AnnotationTask:
        task = self.workspace.metadata.get_task(task_id)
        if task is None:
            raise NotFoundError("task", task_id)
        return task

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

    def _asset_for_annotation_file(self, dataset_id: str, input_path: str, input_format: str):
        path = Path(input_path)
        assets = self.workspace.metadata.list_assets(dataset_id)
        by_filename = {Path(asset.uri).name: asset for asset in assets}
        try:
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


# ── Module-level helpers ───────────────────────────────────────────────────────

def _tenant_to_dict(tenant: SystemTenant) -> dict[str, Any]:
    return {
        "tenant_id": tenant.tenant_id,
        "system_name": tenant.system_name,
        "server_host_name": tenant.server_host_name,
        "target_format": tenant.target_format,
        "api_token": tenant.api_token,
        "created_at": tenant.created_at,
        "connector_type": tenant.connector_type,
        "connector_config": tenant.connector_config,
    }


def _task_to_dict(task: AnnotationTask) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "tenant_id": task.tenant_id,
        "ant_id": task.ant_id,
        "ant_active": task.ant_active,
        "original_classification": task.original_classification,
        "new_classification": task.new_classification,
        "annotation_json": task.annotation_json,
        "original_annotation_json": task.original_annotation_json,
        "external_context": task.external_context,
        "annotated_by": task.annotated_by,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "delivery_status": task.delivery_status,
    }


def _download_bytes(url: str) -> bytes:
    """下載 URL 回傳 bytes（支援 http/https/file）。"""
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https"):
        with urlopen(url, timeout=60) as resp:
            return resp.read()
    elif parsed.scheme == "file":
        path = Path(parsed.path)
        return path.read_bytes()
    else:
        raise ValueError(f"不支援的 URL scheme: {parsed.scheme!r}")


def _parse_annotations_from_zip(
    zf: zipfile.ZipFile,
    names: list[str],
    target_format: str,
    task_id: str,
    images_dir: Path,
) -> dict[str, Any]:
    """從 ZIP 中解析標注，回傳 annotation_json dict。若解析失敗則回傳空 dict。"""
    try:
        # COCO: annotations.json
        coco_candidates = [n for n in names if n == "annotations.json" or n.endswith("/annotations.json")]
        if coco_candidates:
            data = zf.read(coco_candidates[0])
            return json.loads(data.decode("utf-8"))

        # YOLO: labels/ 目錄
        label_files = [n for n in names if n.startswith("labels/") and n.endswith(".txt")]
        if label_files:
            result: dict[str, Any] = {"labels": {}}
            for lf in label_files:
                content = zf.read(lf).decode("utf-8")
                result["labels"][Path(lf).name] = content
            return result

        return {}
    except Exception:
        return {}


def _annotation_from_payload(payload: dict[str, Any]) -> Annotation:
    data = dict(payload)
    geometry_data = data.pop("geometry", None)
    geometry = None
    if geometry_data:
        geometry_type = geometry_data.get("type")
        if geometry_type == "bbox":
            geometry = BBoxGeometry.from_dict(geometry_data)
        elif geometry_type == "polygon":
            from plugins.labeling.domain.core.models import PolygonGeometry
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
