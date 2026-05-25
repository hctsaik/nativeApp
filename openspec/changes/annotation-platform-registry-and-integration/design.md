# Design

## Development Order

```
Phase 0 ── Pre-flight decisions (must complete before writing any DB migration)
    │
Phase 1 ── FormatRegistry  (replaces 4 if/elif chains in services.py)
    │
Phase 2 ── Structured ConversionReport + dry-run export
    │
Phase 3 ── ToolRegistry  (replaces if/elif in labeling_runtime.py; fixes module_012 bugs)
    │
Phase 4 ── IntegrationProfile + ExternalSystemConnector  (requires Phase 0 decisions)
    │
Phase 5 ── Orchestration job API  (replaces job stubs in handlers.py)
```

Phases 1–3 are pure refactors with no new DB tables. They can be shipped independently
and validated by existing regression tests. Phase 4 requires a DB migration and the
three pre-flight decisions from Phase 0. Phase 5 requires Phase 4's job table schema.

---

## Phase 0 — Pre-flight Decisions

These must be recorded as ADRs (Architecture Decision Records) before any code is
written for Phase 4.

### Decision A — Tenancy Model
**Options:**
- Row-level: `tenant_id` column on every table + Row-Level Security
- Schema-level: one SQLite DB file per tenant
- Database-level: one host database per tenant

**Recommendation:** Row-level isolation for Phase 4. SQLite RLS is enforced at query
level by the service layer (not DB-level RLS). All CRUD methods accept an optional
`tenant_id` and filter accordingly. Schema-level migration possible in Phase 5+ if
needed.

**Impact:** `sqlite_store.py` needs `tenant_id` column added to all 6 tables:
`datasets`, `assets`, `schemas`, `annotation_sets`, `review_decisions`, `exports`.

### Decision B — Credential Management
**Options:**
- Local encrypted store (AES-256, key in OS keychain)
- External vault (HashiCorp Vault / AWS Secrets Manager)
- Environment variable references only

**Recommendation:** Local `CredentialStore` backed by OS keychain for Phase 4.
`IntegrationProfile.credential_ref` is an opaque key into the store.
External vault adapter can be added in Phase 5 without changing connector interface.

**Impact:** New `annotation/integrations/credential_store.py`. Credentials never
serialized into `IntegrationProfile` JSON directly.

### Decision C — Schema Pin Mechanism
**Options:**
- `AnnotationSet` stores `schema_id` pointing to current schema (mutable)
- `AnnotationSet` stores `schema_version_ref` pointing to an immutable schema snapshot
- Schema versions are append-only; no delete/update allowed

**Recommendation:** Append-only schema store with `schema_version_ref`. At
`create_annotation_set()` time, a schema snapshot is written and the `annotation_set`
row is pinned to that snapshot's `schema_id`. Subsequent schema edits create a new
version. Existing annotation sets are unaffected.

**Impact:** `sqlite_store.py` schemas table gains `parent_schema_id` and `version_num`.
`annotation_sets` table gains `schema_version_ref` replacing bare `schema_id` use.

---

## Phase 1 — FormatRegistry

### Problem (verified against codebase)
`services.py` has **4 if/elif dispatch blocks**:

| Method | Lines | Formats dispatched |
|---|---|---|
| `prepare_labeling_project()` | 222–227 | x-anylabeling, labelme, isat — **NOTE: tool dispatch, move to Phase 3** |
| `import_annotations()` | 276–290 | labelme, x-anylabeling, isat, coco — mixed with asset logic |
| `import_project_labels()` | 305–322 | labelme, x-anylabeling, isat, yolo-detection, yolo-segmentation |
| `create_export()` | 359–370 | labelme, x-anylabeling, isat, coco, yolo-detection, yolo-segmentation |

`supported_annotation_formats()` (lines 331–339) returns a hardcoded list of 6 entries.

### New Package Layout
```
annotation/formats/
    __init__.py
    contracts.py        # FormatAdapter, FormatDescriptor, FormatCapabilities
    registry.py         # FormatRegistry singleton; register(), get(), list_supported()
    builtins.py         # registers all 6 existing adapters at import time
```

### FormatCapabilities Contract
```python
@dataclass
class FormatCapabilities:
    can_import: bool
    can_export: bool
    requires_asset: bool  # False for COCO (imports without asset_id)
    supports_polygon: bool
    supports_bbox: bool
    supports_classification: bool
    lossless_roundtrip: bool  # True only for labelme / x-anylabeling
```

### Key Implementation Notes
- `_normalize_format()` (currently at services.py lines 462–475) must move into
  `registry.py` so callers normalise once via `registry.get(format_id)`.
- COCO import special case: `import_annotations()` line 276 sets `asset = None` for
  COCO. This must become `FormatCapabilities.requires_asset = False`, not inline logic.
- `prepare_labeling_project()` dispatches on **tool**, not format — leave it for Phase 3.
  Remove only the `import_annotations / import_project_labels / create_export` dispatch.
- All 10 adapter function imports in services.py lines 6–13 removed after Phase 1;
  replaced by `from annotation.formats.registry import get_format_registry`.
- `supported_annotation_formats()` return value shape unchanged (`id`, `name`,
  `can_import`, `can_export`) — populated from `FormatDescriptor` automatically.

### Preserved API (no breaking changes)
- All MCP tool names
- `import_xanylabeling_*`, `prepare_xanylabeling_*` public methods
- `supported_annotation_formats()` return shape

---

## Phase 2 — Structured ConversionReport

### Problem
`ConversionReport` lives in `annotation/core/models.py` (lines 273–282), has 9 fields,
but no `summary` or structured `losses[]` list. `dry_run_export` does not exist.

### ConversionReport Extension
```python
@dataclass
class LossEntry:
    asset_id: str | None
    annotation_id: str | None
    loss_type: str      # "dropped", "approximated", "unsupported", "truncated"
    field: str
    reason: str
    severity: str       # "warning" | "error"

@dataclass
class ConversionReport:
    # Existing fields (all preserved):
    lossless: bool
    dropped_fields: list[str]
    approximated_fields: list[str]
    unsupported_annotations: list[str]
    coordinate_transform: str | None
    class_mapping: dict[str, int | str]
    warnings: list[str]
    source_format_version: str | None
    target_format_version: str | None
    # New fields:
    losses: list[LossEntry]         # structured per-item loss entries
    mapping_version: str | None     # IntegrationProfile schema_mapping version
    summary: str                    # human-readable one-line summary
```

### New Service API
```python
def dry_run_export(
    self,
    annotation_set_id: str,
    export_format: str,
    options: dict | None = None,
) -> ConversionReport:
    """Run export conversion without writing any files. Returns loss report."""
```

### New MCP Tool
`annotation_dry_run_export(annotation_set_id, format, options?)` → ConversionReport

---

## Phase 3 — ToolRegistry

### Problem (verified against codebase)
`labeling_runtime.py` has if/elif at:
- `detect_labeling_tool()` lines 30–39: x-anylabeling / labelme / isat
- `launch_labeling_project()` lines 42–56: x-anylabeling branches completely,
  labelme/isat share `Popen` without env cleanup

Two WDAC bypass implementations:
- `xanylabeling_runtime._command_prefix()` → `python.exe -m anylabeling.app`
- `012_output._launch_xany()` → `python -c "sys.path.insert(...); from anylabeling.app import main; main()"`

Known bug: `012_output._launch_labelme()` line 432 uses `\` (backslash) instead of `/`
for path join — **must fix in Phase 3**.

### New Package Layout
```
annotation/tools/
    __init__.py
    contracts.py        # LabelingToolAdapter, ToolDescriptor, RuntimeStatus
    registry.py         # ToolRegistry; register(), get(), list_supported()
    builtins.py         # x-anylabeling, labelme, isat adapters
```

### ToolDescriptor Contract
```python
@dataclass
class RuntimeStatus:
    available: bool
    executable: str
    version: str | None    # None for labelme/isat (no version detection yet)
    message: str

@dataclass
class ToolDescriptor:
    tool_id: str                   # "x-anylabeling" | "labelme" | "isat"
    display_name: str
    default_output_format: str     # "x-anylabeling" | "labelme" | "isat"
    supports_project_mode: bool    # False for isat (file args not supported)
    supports_file_mode: bool       # True for all three
    detect: Callable[[], RuntimeStatus]
    launch_project: Callable[[Path, dict], None]
    launch_file: Callable[[str, dict], str | None]  # returns error msg or None
```

### Output Path Modes (critical distinction)
- **Project mode** (`launch_labeling_project`): output → `project_dir/labels/`
- **File mode** (`012_output._launch_*`): output → `Path(file_path).parent`

ToolRegistry must expose both modes explicitly. Do not conflate them.

### WDAC Bypass Strategy
Consolidate on the stronger bypass from `012_output._launch_xany()`:
`python -c "sys.path.insert(0, site_packages); from anylabeling.app import main; main()"`

Reason: this works even when the `.exe` trampoline (uv-style) is blocked by WDAC.
The `python.exe -m anylabeling.app` form in `xanylabeling_runtime._command_prefix()`
may fail if `anylabeling` is not on sys.path. Keep old form as fallback only.

### module_006 Compatibility
- `xany_dir` override: ToolRegistry adapter must accept an `executable_override` kwarg
  that maps to `xany_dir` for backwards compatibility.
- `legacy_mode` field: preserved as-is; ToolDescriptor exposes a `legacy_flags` dict.

---

## Phase 4 — IntegrationProfile + ExternalSystemConnector

### Requires Phase 0 Decisions
Do not start Phase 4 until Decisions A, B, C are recorded.

### New Package Layout
```
annotation/integrations/
    __init__.py
    contracts.py            # ExternalSystemConnector ABC, ExternalTask, PushResult
    profiles.py             # load/validate IntegrationProfile JSON
    mappings.py             # FieldMapper, SchemaMapper, StatusMapper
    credential_store.py     # CredentialStore (AES-256 + OS keychain)
    connectors/
        __init__.py
        fake_connector.py   # deterministic fixture for tests
        file_connector.py   # local/UNC file system connector
        rest_connector.py   # generic REST connector (Phase 4 optional)
        oracle_connector.py # behind optional cx_Oracle dependency
```

### IntegrationProfile JSON Schema
```json
{
    "version": "1.0",
    "system_id": "oracle-mes-line-a",
    "tenant_id": "customer-xyz",
    "connector_type": "oracle",
    "credential_ref": "cred:oracle-mes-line-a",
    "format_policy": "warn_and_skip",
    "field_mapping": {
        "external_task_id": "TASK_ID",
        "image_uri": "IMAGE_PATH",
        "label_class": "DEFECT_CODE"
    },
    "schema_mapping": {
        "version": "1.0",
        "mappings": [...]
    }
}
```

### ExternalSystemConnector ABC
```python
class ExternalSystemConnector(ABC):
    @abstractmethod
    def list_tasks(self, query: dict, pagination_token: str | None) -> tuple[list[ExternalTask], str | None]: ...
    @abstractmethod
    def resolve_asset(self, task: ExternalTask) -> ResolvedAsset: ...
    @abstractmethod
    def load_label_schema(self) -> RawLabelSchema: ...
    @abstractmethod
    def push_annotations(self, task_id: str, payload: ExportPayload, mode: PushMode) -> PushResult: ...
    @abstractmethod
    def health_check(self) -> ConnectorHealth: ...
```

### MCP API Impact (backward compatible additions only)
| Existing tool | Change |
|---|---|
| `annotation_create_dataset` | Add optional `integration_profile_id` |
| `annotation_create_export` | Add optional `destination_profile_id` |
| `annotation_ingest_assets` | Accept `connector_uri` in addition to local paths |
| All others | No change |

### DB Migration Required
- All 6 tables gain `tenant_id TEXT NOT NULL DEFAULT ''` column
- New table: `integration_profiles (id, tenant_id, payload, created_at)`
- New table: `jobs (id, tenant_id, job_type, state, profile_id, payload, created_at, updated_at)`
- Enable `PRAGMA journal_mode=WAL` on all connections
- `annotation_sets` gains `schema_version_ref` column

---

## Phase 5 — Orchestration Job API

### Problem
`handlers.py` lines 227–231: `get_job_status` always returns `state: "succeeded"`;
`cancel_job` always returns `state: "not_cancelable"`. No real job table.

**Critical naming risk:** `get_task(task_id)` (line 107) uses `task_id` as an alias for
`annotation_set_id`. Phase 5 introduces real `job_id` entities. These ID namespaces must
be disambiguated before Phase 5 ships.

### New Service API
```python
def create_import_job(self, profile_id: str, query: dict, options: dict) -> dict
def create_export_job(self, annotation_set_id: str, target_profile_id: str, options: dict) -> dict
def dry_run_export_job(self, annotation_set_id: str, target_profile_id: str) -> dict
def get_job_status(self, job_id: str) -> dict    # replaces stub
def cancel_job(self, job_id: str) -> dict        # replaces stub
def get_conversion_report(self, job_id: str) -> ConversionReport
```

### Job State Machine
```
queued → running → succeeded
                 → failed      → (manual retry → queued)
                 → partial     → (resume → running)
```

### AuditLog
- Separate `audit_log` table: `(id, tenant_id, job_id, actor, action, timestamp, payload)`
- Written on every state transition
- No DELETE or UPDATE ever permitted on audit_log rows

### Dead-letter
- Jobs in `failed` state after N retries move to `dead_letter` state
- Dedicated `audit_log` entry with full error detail
- UI and MCP tool to list/inspect dead-letter jobs

---

## Acceptance Criteria (all phases)

| Check | Standard |
|---|---|
| No breaking changes to existing public MCP tool names | All existing tools callable with existing signatures |
| FormatRegistry dispatch covers all 6 formats | `supported_annotation_formats()` returns identical list |
| ConversionReport backward compatible | All 9 existing fields present; new fields optional |
| ToolRegistry covers all 3 tools | `detect_labeling_tool()` returns equivalent results |
| `_launch_labelme()` backslash bug fixed | Path join uses `/` |
| WDAC bypass consolidated | Single implementation, old fallback retained |
| Phase 4 requires tenant_id decision recorded | No Phase 4 DB migration without ADR-A |
| Phase 5 job/task ID disambiguation documented | `get_task` alias relationship documented |
| Existing regression tests pass | `npm run test:python` green after each phase |
