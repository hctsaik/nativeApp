from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .config import WORKSPACE_ROOT

from plugins.labeling.domain.services import AnnotationService
from plugins.labeling.domain.storage.workspace import AnnotationWorkspace

from .handlers import AnnotationMCPHandlers

mcp = FastMCP("annotation-mcp")
_handlers = AnnotationMCPHandlers(AnnotationService(AnnotationWorkspace(WORKSPACE_ROOT)))


@mcp.resource("annotation://datasets")
def annotation_datasets() -> str:
    return _handlers.list_datasets()


@mcp.resource("annotation://schemas/{schema_id}")
def annotation_schema(schema_id: str) -> str:
    return _handlers.get_schema(schema_id)


@mcp.resource("annotation://annotation-sets/{annotation_set_id}")
def annotation_set(annotation_set_id: str) -> str:
    return _handlers.get_asset_annotations(annotation_set_id)


@mcp.tool()
def annotation_create_dataset(name: str, root_uri: str, metadata_json: str = "{}") -> str:
    return _handlers.create_dataset(name, root_uri, metadata_json)


@mcp.tool()
def annotation_list_datasets() -> str:
    return _handlers.list_datasets()


@mcp.tool()
def annotation_ingest_assets(dataset_id: str, image_paths_json: str, copy: bool = True) -> str:
    return _handlers.ingest_assets(dataset_id, image_paths_json, copy)


@mcp.tool()
def annotation_create_schema(
    name: str,
    labels_json: str,
    attribute_schema_json: str = "[]",
    version: str = "1.0",
    schema_id: str | None = None,
) -> str:
    return _handlers.create_schema(name, labels_json, attribute_schema_json, version, schema_id)


@mcp.tool()
def annotation_get_schema(schema_id: str) -> str:
    return _handlers.get_schema(schema_id)


@mcp.tool()
def annotation_create_task(
    dataset_id: str,
    schema_id: str,
    annotations_json: str = "[]",
    source: str = "human",
    created_by: str | None = None,
) -> str:
    """MVP task creation creates the initial annotation set for a dataset/schema."""
    return _handlers.create_annotation_set(dataset_id, schema_id, annotations_json, source, created_by)


@mcp.tool()
def annotation_get_asset_annotations(annotation_set_id: str, asset_id: str | None = None) -> str:
    return _handlers.get_asset_annotations(annotation_set_id, asset_id)


@mcp.tool()
def annotation_get_task(task_id: str) -> str:
    return _handlers.get_task(task_id)


@mcp.tool()
def annotation_list_tasks(tenant_id: str, user_id: str | None = None, ant_active: int | None = None) -> str:
    return _handlers.list_tasks(tenant_id, user_id, ant_active)


@mcp.tool()
def annotation_upsert_annotations(
    annotation_set_id: str,
    annotations_json: str,
    base_version: int | None = None,
    replace: bool = True,
) -> str:
    return _handlers.upsert_annotations(annotation_set_id, annotations_json, base_version, replace)


@mcp.tool()
def annotation_validate_set(annotation_set_id: str) -> str:
    return _handlers.validate_set(annotation_set_id)


@mcp.tool()
def annotation_submit_for_review(annotation_set_id: str) -> str:
    return _handlers.submit_for_review(annotation_set_id)


@mcp.tool()
def annotation_review_task(annotation_set_id: str, decision: str, actor_id: str, comment: str = "") -> str:
    return _handlers.review_task_legacy(annotation_set_id, decision, actor_id, comment)


@mcp.tool()
def annotation_prepare_xanylabeling_project(
    dataset_id: str,
    schema_id: str,
    output_dir: str,
    asset_ids_json: str = "null",
) -> str:
    return _handlers.prepare_xanylabeling_project(dataset_id, schema_id, output_dir, asset_ids_json)


@mcp.tool()
def annotation_prepare_labeling_project(
    tool: str,
    dataset_id: str,
    schema_id: str,
    output_dir: str,
    asset_ids_json: str = "null",
) -> str:
    return _handlers.prepare_labeling_project(tool, dataset_id, schema_id, output_dir, asset_ids_json)


@mcp.tool()
def annotation_detect_xanylabeling() -> str:
    return _handlers.detect_xanylabeling()


@mcp.tool()
def annotation_launch_xanylabeling_project(project_dir: str) -> str:
    return _handlers.launch_xanylabeling_project(project_dir)


@mcp.tool()
def annotation_detect_labeling_tool(tool: str) -> str:
    return _handlers.detect_labeling_tool(tool)


@mcp.tool()
def annotation_launch_labeling_project(tool: str, project_dir: str) -> str:
    return _handlers.launch_labeling_project(tool, project_dir)


@mcp.tool()
def annotation_import_xanylabeling(dataset_id: str, schema_id: str, asset_id: str, input_path: str) -> str:
    return _handlers.import_xanylabeling(dataset_id, schema_id, asset_id, input_path)


@mcp.tool()
def annotation_import_xanylabeling_project_labels(dataset_id: str, schema_id: str, labels_dir: str) -> str:
    """Import all LabelMe JSON files from an X-AnyLabeling labels/ directory.

    Automatically matches each JSON to a dataset asset by comparing the imagePath
    field in the JSON to asset filenames. Returns a merged AnnotationSet and a
    report listing any files that could not be matched.
    """
    return _handlers.import_xanylabeling_project_labels(dataset_id, schema_id, labels_dir)


@mcp.tool()
def annotation_import_annotations(
    dataset_id: str,
    schema_id: str,
    input_format: str,
    input_path: str,
    asset_id: str | None = None,
) -> str:
    return _handlers.import_annotations(dataset_id, schema_id, input_format, input_path, asset_id)


@mcp.tool()
def annotation_import_project_labels(dataset_id: str, schema_id: str, input_format: str, labels_dir: str) -> str:
    return _handlers.import_project_labels(dataset_id, schema_id, input_format, labels_dir)


@mcp.tool()
def annotation_supported_annotation_formats() -> str:
    return _handlers.supported_annotation_formats()


@mcp.tool()
def annotation_create_export(
    annotation_set_id: str,
    export_format: str,
    output_dir: str,
    purpose: str = "preview",
) -> str:
    return _handlers.create_export(annotation_set_id, export_format, output_dir, purpose)


@mcp.tool()
def annotation_get_export(export_id: str) -> str:
    return _handlers.get_export(export_id)


@mcp.tool()
def annotation_get_job_status(job_id: str) -> str:
    return _handlers.get_job_status(job_id)


@mcp.tool()
def annotation_cancel_job(job_id: str) -> str:
    return _handlers.cancel_job(job_id)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
