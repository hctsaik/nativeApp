# Annotation Workflow Extensions

## Why

The current annotation workflow (module_010 through module_016) hardcodes local
file access and local SQLite as the only data source. This blocks two important
directions:

1. Teams that store their image library and annotation results in a central SQL
   database or behind a REST service cannot use the workflow without manual
   file exports and imports.

2. The workflow modules are embedded in the nativeApp monorepo and cannot be
   adopted by other teams as a standalone starting point without forking the
   entire repository.

Additionally, three functional gaps remain that block production annotation
work for any team size:

- There is no way to rename, merge, or delete labels globally across all
  annotation files when the label taxonomy changes.
- There is no in-app visual review of annotated images with bbox overlays drawn.
  Users must open X-AnyLabeling externally to verify annotation quality.
- Export runs without any pre-flight quality checks. Empty images, tiny bounding
  boxes, and classification-annotation mismatches silently enter the training set.

## What Changes

Introduce a connector framework and three new workflow features:

- A `DataConnector` abstraction layer that decouples data source (local file,
  SQL, REST) from the annotation logic. Existing local-file mode continues to
  work with zero configuration changes.
- A `connector.yaml` sidecar configuration file that lets each deployment choose
  its data source without modifying module code.
- A `LocalFileConnector` that implements the new interface and wraps existing
  behavior, providing backwards compatibility.
- A `SqlConnector` (SQLAlchemy) and `RestConnector` (requests) for teams with
  centralized data infrastructure.
- A `sync_queue` table in the local SQLite manifest database that enables
  offline annotation with deferred push to remote.
- `module_017` Label Manager: rename, merge, delete, and near-duplicate-detect
  labels globally across all X-AnyLabeling JSON files in a manifest.
- `module_018` Review Gallery: visual grid of annotated images with PIL-rendered
  bbox overlays, filterable by label, status, and confidence.
- Pre-export validation in `module_014`: a blocking pre-flight check report
  before each export run.
- A `cim_annotation/` submodule directory layout suitable for extraction as a
  git submodule so other teams can adopt the connector framework and module
  templates without forking nativeApp.

## Scope

In scope:

- `PullConnector` and `PushConnector` abstract base classes.
- `FetchedItem`, `AnnotationPayload`, and `PushResult` data models.
- `LocalFileConnector` implementation.
- `SqlConnector` implementation (SQLAlchemy, shared-mount image access).
- `RestConnector` implementation (requests, streaming image download, Bearer
  token auth).
- `ConnectorFactory` with `importlib`-based custom connector loading.
- `connector.yaml` configuration schema and env-var credential injection.
- `sync_queue` table DDL and `SyncEngine` for offline-first push with conflict
  detection.
- `module_017` Label Manager (scan, rename, merge, delete, near-duplicate).
- `module_018` Review Gallery (grid, filter, detail view, PIL overlay).
- Pre-export validation integration in `module_014`.
- `cim_annotation/` directory layout documentation for git submodule extraction.

Out of scope:

- Multi-user lock management or assignment queues.
- gRPC connector implementation.
- OAuth or SSO authentication for REST connector.
- Changes to `annotation-core` canonical model or MCP surface.
- Kubernetes or cloud deployment of the REST service itself.
- Any GUI automation.

## Decisions

- The connector interface is optional. Absence of `connector.yaml` activates
  `LocalFileConnector` automatically, preserving all existing behavior.
- Credentials are injected as environment variables by `engine.py
  _make_env()`, following the existing `CIM_*` env var pattern. They are
  never stored in `tools.sqlite` or module config files.
- The `sync_queue` conflict rule is last-local-write wins unless the remote
  record was updated after the local annotation session started, in which case
  the item is flagged as conflict for manual resolution.
- The `cim_annotation/` submodule boundary is documented but not extracted in
  this change. Extraction happens when a second consumer team is ready to adopt.
- `module_017` must use atomic write (`tmp` + `os.replace`) for every file it
  modifies to survive interruption without data loss.
- `module_018` renders overlays with PIL `ImageDraw` cached by `(path, mtime)`
  to avoid per-rerun PIL calls in accordance with the platform's Streamlit
  output performance rules.

## Success Criteria

- A team with a PostgreSQL image database can configure `connector.yaml` to
  pull image metadata and push annotation results without modifying any module
  code.
- A team with no external database continues to use the workflow identically to
  before this change.
- An annotator can rename a label across all JSON files in a manifest from a
  single UI action with a two-step confirmation and atomic file writes.
- An annotator can visually browse a paginated grid of annotated images with
  bbox overlays drawn and filter by label or annotation status.
- Running module_014 Export shows a validation report before writing any files
  if images with zero annotations, bbox area below threshold, or
  classification-annotation mismatches are detected.
