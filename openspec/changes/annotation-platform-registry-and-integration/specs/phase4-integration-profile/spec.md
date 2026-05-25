# Phase 4 — IntegrationProfile + ExternalSystemConnector Spec

## Objective

Introduce the integration layer that allows external systems (Oracle MES, REST APIs,
file systems) to connect to the annotation platform without polluting annotation
core with customer-specific SQL, table names, or credentials.

## Hard Prerequisites

**All three Phase 0 decisions must be recorded as ADRs before writing any code.**

- ADR-A: Tenancy model selected (recommendation: row-level `tenant_id`)
- ADR-B: Credential management architecture selected (recommendation: local CredentialStore)
- ADR-C: Schema pin mechanism selected (recommendation: append-only schema with `schema_version_ref`)

## Requires

Phase 1 (FormatRegistry) and Phase 3 (ToolRegistry) complete.

## Files to Create

```
annotation/integrations/__init__.py
annotation/integrations/contracts.py
annotation/integrations/profiles.py
annotation/integrations/mappings.py
annotation/integrations/credential_store.py
annotation/integrations/connectors/__init__.py
annotation/integrations/connectors/fake_connector.py
annotation/integrations/connectors/file_connector.py
```

## DB Migration Required

```sql
-- Enable WAL on all connections (in sqlite_store.py connect())
PRAGMA journal_mode=WAL;

-- tenant_id on all existing tables
ALTER TABLE datasets           ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '';
ALTER TABLE assets             ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '';
ALTER TABLE schemas            ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '';
ALTER TABLE annotation_sets    ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '';
ALTER TABLE review_decisions   ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '';
ALTER TABLE exports            ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '';

-- schema versioning (Decision C)
ALTER TABLE schemas            ADD COLUMN parent_schema_id TEXT;
ALTER TABLE schemas            ADD COLUMN version_num INTEGER NOT NULL DEFAULT 1;
ALTER TABLE annotation_sets    ADD COLUMN schema_version_ref TEXT;

-- new tables
CREATE TABLE integration_profiles (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL DEFAULT '',
    payload     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE jobs (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL DEFAULT '',
    job_type    TEXT NOT NULL,
    state       TEXT NOT NULL DEFAULT 'queued',
    profile_id  TEXT,
    payload     TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE audit_log (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL DEFAULT '',
    job_id      TEXT,
    actor       TEXT NOT NULL DEFAULT 'system',
    action      TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    payload     TEXT NOT NULL DEFAULT '{}'
);
```

## ExternalSystemConnector ABC (`contracts.py`)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class PaginationToken:
    value: str | None    # None = first page; opaque string per connector

@dataclass
class ExternalTask:
    external_id: str
    image_uri: str
    metadata: dict[str, Any]
    rework_reason: str | None = None

@dataclass
class ResolvedAsset:
    asset_type: str      # "local_path" | "remote_url" | "blob_stream"
    value: str           # local file path, presigned URL, or temp file path
    ttl_seconds: int | None = None   # for presigned URLs

@dataclass
class RawLabelSchema:
    raw: dict[str, Any]
    source_format: str   # connector declares what format the schema data is in

@dataclass
class ExportPayload:
    format_id: str
    data: Any
    conversion_report: dict  # ConversionReport.to_dict()

@dataclass
class PushResult:
    success: bool
    rows_written: int
    external_ref: str | None
    error: str | None

@dataclass
class ConnectorHealth:
    connected: bool
    latency_ms: int | None
    version: str | None
    error: str | None

class ExternalSystemConnector(ABC):
    @abstractmethod
    def list_tasks(
        self,
        query: dict[str, Any],
        pagination_token: PaginationToken,
    ) -> tuple[list[ExternalTask], PaginationToken]: ...

    @abstractmethod
    def resolve_asset(self, task: ExternalTask) -> ResolvedAsset: ...

    @abstractmethod
    def load_label_schema(self) -> RawLabelSchema: ...

    @abstractmethod
    def push_annotations(
        self,
        task_id: str,
        payload: ExportPayload,
        mode: str,      # "insert_only" | "upsert" | "replace_all"
    ) -> PushResult: ...

    @abstractmethod
    def health_check(self) -> ConnectorHealth: ...
```

## IntegrationProfile JSON Schema (`profiles.py`)

```json
{
  "$schema": "https://cim.internal/schemas/integration-profile/v1.json",
  "version": "1.0",
  "system_id": "oracle-mes-line-a",
  "tenant_id": "customer-xyz",
  "connector_type": "oracle",
  "capability_matrix": {
    "supports_batch_commit": false,
    "idempotency_key_field": null,
    "push_modes": ["upsert"],
    "pull_mode": "poll",
    "pagination_style": "keyset"
  },
  "credential_ref": "cred:oracle-mes-line-a",
  "format_policy": "warn_and_skip",
  "field_mapping": {
    "external_task_id": "TASK_ID",
    "image_uri": "IMAGE_PATH",
    "label_class": "DEFECT_CODE"
  },
  "schema_mapping": {
    "version": "1.0",
    "mappings": [
      {"external": "OK", "canonical": "pass"},
      {"external": "NG", "canonical": "defect"}
    ]
  }
}
```

## CredentialStore (`credential_store.py`)

```python
class CredentialStore:
    def store(self, ref: str, secret: str) -> None:
        """Encrypts and stores. Key must not be logged."""
    def retrieve(self, ref: str) -> str:
        """Returns plaintext secret. Raises KeyError if not found."""
    def rotate(self, ref: str, new_secret: str) -> None: ...
    def delete(self, ref: str) -> None: ...
```

Implementation: AES-256-GCM encryption; master key stored in OS keychain
(`keyring` library). Ciphertext persisted in a local `credentials.db` (separate from
annotation SQLite to prevent accidental dump).

## MCP API Changes (backwards compatible)

```
annotation_create_dataset(name, root_uri, metadata?, integration_profile_id?)
annotation_ingest_assets(dataset_id, image_paths|connector_uris, copy?, profile_id?)
annotation_create_export(annotation_set_id, format, output_dir?, destination_profile_id?)
```

All new parameters are **optional** — callers that omit them get current behaviour.

## FakeConnector (`connectors/fake_connector.py`)

Deterministic connector for tests:
- `list_tasks`: returns configured fixture tasks
- `resolve_asset`: returns a real local image path from test fixtures
- `push_annotations`: records push calls for assertion
- `health_check`: always returns `connected=True`

## Tests to Add

```
tests/annotation/test_integration_profile.py
    - test_load_valid_profile
    - test_profile_missing_tenant_id_raises
    - test_credential_ref_not_inlined_in_profile
    - test_schema_mapping_version_required

tests/annotation/test_connectors.py
    - test_fake_connector_list_tasks
    - test_fake_connector_resolve_asset
    - test_fake_connector_push_annotations
    - test_file_connector_resolve_local_path
    - test_file_connector_unc_path_not_reachable_raises

tests/annotation/test_tenant_isolation.py
    - test_dataset_scoped_to_tenant
    - test_cross_tenant_query_returns_empty

tests/annotation/test_sqlite_wal.py
    - test_journal_mode_is_wal
```

## Acceptance Criteria

- [ ] ADR-A, ADR-B, ADR-C written and stored in `openspec/adr/`
- [ ] DB migration applied; all 6 tables have `tenant_id` column
- [ ] `PRAGMA journal_mode=WAL` set on every connection
- [ ] `IntegrationProfile` loads and validates from JSON
- [ ] `CredentialStore` encrypts at rest; plaintext never in DB
- [ ] `FakeConnector` passes all contract tests
- [ ] `FileConnector` resolves local paths and UNC paths
- [ ] MCP tools backward compatible (omitted new params = previous behaviour)
- [ ] `npm run test:python` fully green
