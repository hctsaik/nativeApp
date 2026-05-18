# Tasks: Annotation Common Component

## Phase 0 - Contract Decisions

- [x] Confirm `annotation-core` as the only canonical truth.
- [x] Confirm MVP geometry: image asset, bbox, polygon, image-level classification.
- [x] Confirm no multi-user collaboration in MVP.
- [x] Confirm review and approval workflow.
- [x] Confirm local workspace plus SQLite as the MVP storage implementation.
- [x] Confirm draft export for preview and approved export for training/publish.

## Phase 1 - Core Model

- [x] Define `Dataset`.
- [x] Define `ImageAsset`.
- [x] Define `LabelSchema`, `LabelDef`, and `AttributeDef`.
- [x] Define `AnnotationSet`.
- [x] Define `Annotation`.
- [x] Define bbox geometry.
- [x] Define polygon geometry.
- [x] Define image-level classification.
- [ ] Define `Task`.
- [ ] Define `Job`.
- [x] Define `ArtifactRef`.
- [x] Define `ReviewDecision`.
- [x] Define provenance fields.
- [ ] Define audit records.
- [x] Add unit tests for model serialization and schema compatibility.

## Phase 2 - State And Validation

- [x] Implement annotation set state transitions.
- [ ] Implement task and job state transitions.
- [x] Implement review decision records.
- [x] Implement schema version validation.
- [x] Implement label validation.
- [x] Implement allowed geometry validation.
- [x] Implement bbox validation.
- [x] Implement polygon validation.
- [x] Implement image classification validation.
- [x] Implement required attribute validation.
- [x] Implement approved-set overwrite protection.
- [x] Add unit tests for all validation rules.

## Phase 3 - Storage And Artifacts

- [x] Define `MetadataStore` interface.
- [x] Define `ArtifactStore` interface.
- [x] Implement local SQLite metadata store.
- [x] Implement local workspace artifact store.
- [x] Implement checksum-based asset ingest.
- [x] Implement canonical annotation JSON writer.
- [ ] Implement canonical annotation JSON reader.
- [x] Implement manifest writer.
- [ ] Implement manifest reader.
- [ ] Add storage migration tests.
- [x] Add idempotent ingest tests.

## Phase 4 - Application Services

- [x] Implement `create_dataset`.
- [x] Implement `list_datasets`.
- [x] Implement `ingest_assets`.
- [x] Implement `create_schema`.
- [x] Implement `get_schema`.
- [x] Implement MVP `create_task` as annotation set creation.
- [x] Implement MVP `get_task`.
- [x] Implement MVP `list_tasks`.
- [x] Implement `get_asset_annotations`.
- [x] Implement `upsert_annotations`.
- [x] Implement `validate_set`.
- [x] Implement `submit_for_review`.
- [x] Implement `review_task`.
- [x] Implement `create_export` contract.
- [x] Implement `get_export`.
- [x] Implement synchronous MVP `get_job_status`.
- [x] Implement synchronous MVP `cancel_job`.

## Phase 5 - MCP API

- [x] Add `annotation-mcp` package or module.
- [x] Add common resource handlers.
- [x] Add common tool schemas.
- [x] Add common tool handlers.
- [x] Add structured error responses.
- [x] Add MCP handler tests.
- [x] Keep `cim-gui-mcp` separate from annotation MCP.

## Phase 6 - Documentation

- [x] Document canonical model.
- [x] Document workspace layout.
- [x] Document state machines.
- [x] Document MCP resources and tools.
- [x] Document validation issue format.
- [x] Document conversion report format.
- [x] Document domain pack extension rules.

## Acceptance

- [x] A dataset can ingest image assets into the local workspace.
- [x] A schema can define bbox, polygon, and image classification requirements.
- [x] An annotation set can be created, updated, validated, submitted, approved, rejected, or sent back for changes.
- [x] Draft exports are allowed only as preview exports.
- [x] Approved exports are allowed for training/publish workflows.
- [x] Validation issues include severity, code, field path, and target IDs.
- [x] Adapter/export conversion reports identify lossy fields.
- [x] Domain-specific wrappers are optional and do not change core contracts.
