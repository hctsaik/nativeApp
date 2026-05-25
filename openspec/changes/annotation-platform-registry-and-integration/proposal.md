# Annotation Platform Registry and External Integration

## Why

The annotation platform's format dispatch and tool launch logic is scattered across
`services.py` as a series of `if/elif` chains, and labeling tool launch is duplicated
across `labeling_runtime.py`, `xanylabeling_runtime.py`, and individual module output
pages. There is no plugin model — adding a new format or tool requires editing the core
service file. Integration with external systems (Oracle MES, REST APIs, file systems) has
no defined contract, and there is no stable way for external data to enter the canonical
annotation model without polluting core with customer-specific SQL or API details.

This change introduces:

1. A **FormatRegistry** that replaces if/elif dispatch and makes format adapters
   first-class, pluggable descriptors.
2. A **Structured ConversionReport** with dry-run export so callers can see format
   conversion losses before committing.
3. A **ToolRegistry** that normalises GUI tool preparation and launch behind a
   single contract, eliminating duplicated launch logic across modules.
4. An **IntegrationProfile + ExternalSystemConnector** layer that lets customer-specific
   Oracle/REST/file configurations live outside the annotation core.
5. An **Orchestration job API** that wraps import → labeling → validate → export into
   trackable, retryable jobs with full audit trails.

## What Changes

### Phase 1 — FormatRegistry
- New package `annotation/formats/` with `contracts.py`, `registry.py`, `builtins.py`.
- `AnnotationService` format-dispatching methods (`supported_annotation_formats`,
  `create_export`, `import_annotations`, `import_project_labels`) rewritten to read
  from the registry.
- All existing public API names, MCP tool names, and legacy aliases preserved.

### Phase 2 — Structured ConversionReport + dry-run export
- `ConversionReport` extended with `lossless`, `losses[]`, `mapping_version`, `summary`.
- New `dry_run_export(annotation_set_id, format, options)` service API and MCP tool.
- All format adapters emit structured loss entries for unsupported geometry.

### Phase 3 — ToolRegistry
- New package `annotation/tools/` with `contracts.py`, `registry.py`, `builtins.py`.
- `prepare_labeling_project` and `launch_labeling_project` rewritten to dispatch
  through the registry.
- module_006 updated to read ToolRegistry; legacy `xany_dir` / `legacy_mode` fields
  preserved.
- module_012 launch helpers (`_launch_xany`, `_launch_labelme`, `_launch_isat`)
  remain functional; a unified `launch_tool(tool_id, file_path)` alias is added.

### Phase 4 — IntegrationProfile + ExternalSystemConnector
- New package `annotation/integrations/` with connector contracts, profile loader,
  schema/field mapping engine, and initial `FileConnector` + `FakeConnector`.
- `IntegrationProfile` JSON schema defined: `version`, `system_id`, `tenant_id`,
  `format_policy`, `field_mapping`, `schema_mapping`, `credential_ref`.
- Oracle SQL, table names, REST URLs, credentials never enter annotation core.
- **Requires pre-flight decision: tenancy model, credential architecture, schema pin.**

### Phase 5 — Orchestration job API
- High-level `create_import_job`, `create_export_job`, `dry_run_export_job`,
  `get_job_status`, `get_conversion_report` replacing the current stub handlers.
- All jobs record `profile_version`, `mapping_version`, `format_adapter_version`.
- `AuditLog` written for every job completion (append-only).
- Dead-letter handling for fatal errors.

## Pre-flight Decisions Required Before Phase 4

Three architectural decisions must be made before writing the first DB migration
for Phase 4. Changing these later is expensive.

| Decision | Options | Default recommendation |
|---|---|---|
| **Tenancy model** | row-level (`tenant_id` + RLS) / schema-level / DB-level | Row-level — simplest to start; migrate later if needed |
| **Credential management** | local encrypted store / external vault (HashiCorp / AWS SM) | Local AES-256 encrypted store with rotation API; vault integration in Phase 5+ |
| **Schema pin mechanism** | AnnotationSet stores `schema_version_ref`; SchemaStore is append-only | Each AnnotationSet pins to an immutable schema snapshot at creation time |

## Impact

- `sidecar/python-engine/annotation/services.py` — format dispatch rewritten (Phase 1)
- `sidecar/python-engine/annotation/adapters/common.py` — ConversionReport extended (Phase 2)
- `sidecar/python-engine/annotation/adapters/*.py` — wrap into format/tool adapters (Phase 1, 3)
- `sidecar/python-engine/annotation/adapters/labeling_runtime.py` — dispatch rewritten (Phase 3)
- `sidecar/python-engine/scripts/module_006/` — ToolRegistry integration (Phase 3)
- `sidecar/python-engine/scripts/module_012/` — unified launch alias (Phase 3)
- `mcp/annotation_mcp/handlers.py` — job stubs replaced (Phase 5)
- `sidecar/python-engine/annotation/storage/sqlite_store.py` — WAL + tenant_id (Phase 4)

## Not Changing

- Public MCP tool names (`annotation_create_dataset`, `annotation_ingest_assets`, etc.)
- Existing X-AnyLabeling compatibility API (`import_xanylabeling_*`, `prepare_xanylabeling_*`)
- module_009 X-AnyLabeling launch automation (until Phase 3 is stable)
- `module_008` video export format selection (migrated in Phase 3, batch 2)
- Any existing regression test contract
