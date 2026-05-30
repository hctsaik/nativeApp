# Tasks: Annotation Workflow Extensions

> ⚠️ **此 Change 已完成並被新架構取代（2026-05-29）**
> 原計劃的「擴展 annotation_workflow sheet」已被合併重構為單一「🐜 影像標註」sheet（sheet-annotation）。
> 相關 sheet 設定現在由 `sidecar/python-engine/sheets/annotation.yaml` 驅動。

## Phase 0 — Foundation Models and Factory

- [ ] Create `sidecar/python-engine/cim_annotation/` package directory with `__init__.py`.
- [ ] Define `FetchedItem`, `AnnotationPayload`, `PushResult` dataclasses in `models.py`.
- [ ] Define `PullConnector` and `PushConnector` ABCs in `connectors/base.py`.
- [ ] Implement `LocalFileConnector` in `connectors/local_file.py`.
  - `fetch_page` reads from `manifest.sqlite` items table.
  - `resolve_image` returns `Path(item.image_url)` directly (shared local path).
  - `push_batch` writes X-AnyLabeling JSON alongside images (current module behavior).
- [ ] Implement `ConnectorFactory.build()` in `connectors/factory.py`.
  - Falls back to `LocalFileConnector` when `connector.yaml` is absent.
  - Supports `local_file`, `sql`, `rest`, `custom` types.
  - `custom` type loads connector class via `importlib.import_module`.
- [ ] Add `CIM_CONNECTOR_CONFIG` env var injection in `engine.py _make_env()`.
- [ ] Add `secrets/connector_creds.json` reading in `engine.py _make_env()`.
  - Inject `CIM_CONNECTOR_DSN`, `CIM_CONNECTOR_TOKEN`, `CIM_CONNECTOR_BASE_URL`.
- [ ] Write unit tests for `LocalFileConnector` fetch and push round-trip.
- [ ] Write unit tests for `ConnectorFactory` fallback and type dispatch.

## Phase 1 — module_017 Label Manager

- [ ] Create `cim_annotation/label_ops.py` with:
  - `scan_labels(items) -> dict[str, list[str]]`
  - `find_near_duplicates(labels, threshold=0.8) -> list[tuple[str, str, float]]`
  - `rename_label(items, old, new) -> int`
  - `merge_labels(items, sources, target) -> int`
  - `delete_label(items, label) -> int`
  - All file writes use `tmp + os.replace` atomic pattern.
- [ ] Create `scripts/module_017/plugin.yaml`.
- [ ] Create `scripts/module_017/_config.py` (shared manifest, settings persistence).
- [ ] Create `scripts/module_017/017_input.py`.
  - Show shared manifest info banner.
  - Return `{"manifest_id": str}`.
- [ ] Create `scripts/module_017/017_process.py`.
  - Call `label_ops.scan_labels` and `label_ops.find_near_duplicates`.
  - Return label stats and near-duplicate pairs.
  - Accept action params: `{"action": "rename"|"merge"|"delete", ...}`.
- [ ] Create `scripts/module_017/017_output.py`.
  - Left column: filterable label stats dataframe + near-duplicate warning.
  - Right column tabs: Rename / Merge / Delete with two-step confirmation.
- [ ] Add `module_017` tab to `annotation_workflow`（已廢棄） via `engine.py _initialize()` migration.
- [ ] Add `module_017` to `scripts/sheets/annotation_workflow/sheet.yaml`（已廢棄）.
- [ ] Write unit tests for `label_ops` in `017_process_test.py`.
  - `scan_labels` counts shapes and flags correctly.
  - `rename_label` renames in both shapes and flags.classification.
  - `merge_labels` calls rename for each source.
  - `delete_label` removes shapes and clears flags.
  - Atomic write: `.tmp` file removed after `os.replace`.
  - Interrupted write does not corrupt the original file.
  - Near-duplicate detection finds "Cat" / "cat" pair.

## Phase 2 — module_018 Review Gallery

- [ ] Create `scripts/module_018/plugin.yaml`.
- [ ] Create `scripts/module_018/_config.py`.
- [ ] Create `scripts/module_018/018_input.py`.
  - Show shared manifest info banner.
  - Return `{"manifest_id": str}`.
- [ ] Create `scripts/module_018/018_process.py`.
  - Scan manifest items for annotation status and shape counts.
  - Return items list with annotation metadata for filtering.
- [ ] Create `scripts/module_018/018_output.py`.
  - Filter sidebar: label multiselect, status selectbox, min-bbox slider.
  - Gallery grid: 3 columns, PAGE_SIZE=30, prev/next pagination.
  - `_render_thumb` cached by `(img_path, ann_path, mtime)` using PIL ImageDraw.
  - Detail view on thumbnail click: full-size overlay + shapes dataframe.
  - "Open in X-AnyLabeling" button via subprocess.
  - "Flag for re-annotation" button writes `.flag` sidecar file.
  - Flagged items show yellow border on thumbnail.
- [ ] Add `module_018` tab to `annotation_workflow`（已廢棄） via engine.py migration.
- [ ] Add `module_018` to sheet.yaml.
- [ ] Write unit tests for `018_process.py` (item scan + filter logic).

## Phase 3 — Pre-export Validation in module_014

- [ ] Add `_validate_pre_export(items, shapes_map, classifications) -> list[ValidationIssue]`
  to `014_process.py`.
  - `NO_ANNOTATION` warning: image has no shapes and no classification.
  - `TINY_BBOX` warning: bbox area below `MIN_BBOX_AREA` (default 100 px²).
  - `MISSING_CLASSIFICATION` warning: image has bbox but no classification when
    classifications dict is non-empty (classification task was active).
- [ ] Add `ValidationIssue` dataclass (severity, code, item_id, message).
- [ ] Surface validation issues in `014_output.py` before showing export paths.
  - Collapsible `st.expander("Pre-export Validation")`.
  - Error severity: block export, show st.error.
  - Warning severity: show st.warning + override checkbox.
- [ ] Add validation tests to `014_process_test.py`.
  - Empty image detected as `NO_ANNOTATION`.
  - Tiny bbox detected as `TINY_BBOX`.
  - Bbox-without-classification detected as `MISSING_CLASSIFICATION`.
  - Clean dataset produces empty issues list.

## Phase 4 — SqlConnector

- [ ] Implement `SqlConnector` in `connectors/sql_connector.py`.
  - Constructor: `dsn: str`, `image_root: Path | None`.
  - `fetch_page`: SELECT from `annotation_items` with LIMIT/OFFSET.
  - `resolve_image`: symlink to shared-mount path when `image_root` is set.
  - `push_batch`: PostgreSQL/MySQL upsert to `annotation_results`.
  - `check_remote_version`: SELECT updated_at for given image_ids.
- [ ] Add SQLAlchemy to `requirements.txt` as optional dependency.
- [ ] Write integration tests for `SqlConnector` using SQLite in-memory DSN.
  - `fetch_page` returns correct FetchedItem list.
  - `push_batch` upserts annotation results.
  - `check_remote_version` returns updated_at map.

## Phase 5 — RestConnector and SyncEngine

- [ ] Implement `RestConnector` in `connectors/rest_connector.py`.
  - `fetch_page`: GET `/api/v1/images?offset=N&limit=N`.
  - `resolve_image`: streaming download to local cache, skip on hash match.
  - `push_batch`: POST `/api/v1/annotations/batch`.
  - `check_remote_version`: POST `/api/v1/annotations/versions`.
- [ ] Add `sync_queue` table DDL to `_manifest_db.py` `_SCHEMA`.
  - Columns: id, item_id, manifest_id, local_updated_at, remote_ref, status.
  - Status CHECK constraint: pending | synced | conflict.
- [ ] Implement `SyncEngine` in `cim_annotation/sync_engine.py`.
  - `run_once(manifest_id, push_connector, session_start_at)`.
  - Conflict detection: `remote_updated_at > session_start_at` → status=conflict.
  - Non-conflict: call `push_batch`, update status and remote_ref on success.
  - `ConnectionError`: leave all items pending, return gracefully.
- [ ] Integrate `SyncEngine.run_once` trigger into `012_output.py`
  (called after mtime-change detection, if push connector is active).
- [ ] Write unit tests for `SyncEngine` with a mock push connector.
  - Pending items are pushed and marked synced.
  - Conflict items are flagged and not pushed.
  - ConnectionError leaves items pending.

## Phase 6 — Distribution Layout and Documentation

- [ ] Add `CONNECTOR_GUIDE.md` to `sidecar/python-engine/cim_annotation/`:
  - How to write a custom connector.
  - How to configure `connector.yaml`.
  - How to set up `secrets/connector_creds.json`.
  - How to extract `cim_annotation/` as a git submodule.
- [ ] Add `module_017` and `module_018` docs to `docs/modules/`.
- [ ] Update `docs/modules/sheet-annotation_workflow.md`（已廢棄） with new tabs.
- [ ] Update `docs/MODULES.md` index with new modules and connector guide.
- [ ] Add `connector.yaml.example` to `scripts/module_010/` as adoption template.

## Acceptance

- [ ] A team configures `connector.yaml` with `type: sql` and pulls image
  metadata from a SQLite test database without modifying module code.
- [ ] A team with no `connector.yaml` continues to use all existing modules
  identically to before this change.
- [ ] Renaming label "Cat" to "cat" across a 100-image manifest completes
  atomically; no `.tmp` file remains if the process is interrupted mid-run.
- [ ] Review Gallery renders PIL bbox overlays in a paginated grid with label
  filter and opens X-AnyLabeling on button click.
- [ ] Running Export on a manifest with one unannotated image shows a
  `NO_ANNOTATION` warning in the pre-export report before writing any files.
- [ ] SyncEngine pushes pending annotations to a mock REST connector and marks
  them synced; a conflict item is flagged and not pushed.
