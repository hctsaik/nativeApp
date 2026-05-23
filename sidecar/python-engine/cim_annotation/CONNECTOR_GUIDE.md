# CIM Annotation — Connector Guide

## Overview

The `cim_annotation` package decouples annotation workflows from specific data sources via two abstract interfaces:

- **`PullConnector`** — fetches image items from a source (folder, SQL, REST API)
- **`PushConnector`** — pushes completed annotation results back to the source

By default every module uses **`LocalFileConnector`**, which reads images from disk and writes X-AnyLabeling JSON sidecars — identical to the original behaviour before this abstraction was introduced.  No configuration is needed for this mode.

---

## Quick Start

### Default (local files — zero config)

No `connector.yaml` needed. Existing modules work without any change.

### SQL database

Create `connector.yaml` in the module directory (e.g. `scripts/module_010/connector.yaml`):

```yaml
connector:
  type: sql
  sql:
    dsn: "postgresql+psycopg2://user:password@host:5432/mydb"
    pull_query: "SELECT id, file_path, width, height FROM images WHERE active=1"
    push_table: "annotations"
    push_id_column: "image_id"
    push_json_column: "xanylabeling_json"
    push_updated_at_column: "updated_at"
```

Or use an environment variable for the DSN (recommended for production):

```yaml
connector:
  type: sql
  sql:
    dsn_env: CIM_CONNECTOR_DSN          # reads os.environ["CIM_CONNECTOR_DSN"]
    pull_query: "SELECT id, file_path FROM images"
    push_table: "annotations"
    push_id_column: "image_id"
    push_json_column: "xanylabeling_json"
    push_updated_at_column: "updated_at"
```

Set the env var in `secrets/connector_creds.json` (injected automatically by engine.py):

```json
{
  "dsn": "postgresql+psycopg2://user:password@host:5432/mydb"
}
```

### REST API

```yaml
connector:
  type: rest
  rest:
    base_url: "https://api.example.com"
    token_env: CIM_CONNECTOR_TOKEN
    pull_path: "/images"
    pull_page_param: "offset"
    pull_limit_param: "limit"
    pull_items_key: "data"
    push_path: "/annotations/{item_id}"
    push_method: "POST"
    version_path: "/annotations/versions"
```

### Custom connector

```yaml
connector:
  type: custom
  custom:
    module: my_package.connectors
    class: MyConnector
    config:
      host: localhost
      port: 8080
```

The class must implement `PullConnector` and/or `PushConnector` from `cim_annotation.connectors.base`.

---

## Connector Interfaces

### PullConnector

```python
class PullConnector(ABC):
    def fetch_page(self, offset: int, limit: int) -> list[FetchedItem]: ...
    def resolve_image(self, item: FetchedItem, local_dir: Path) -> Path: ...
    def fetch_all(self, local_dir: Path, page_size: int = 200) -> Iterator[FetchedItem]: ...
```

### PushConnector

```python
class PushConnector(ABC):
    def push_batch(self, payloads: list[AnnotationPayload]) -> list[PushResult]: ...
    def check_remote_version(self, item_ids: list[str]) -> dict[str, str]: ...
```

---

## Offline-First Sync

For unreliable networks, use `SyncEngine` to buffer pushes locally:

```python
from cim_annotation.sync_engine import SyncEngine
from cim_annotation.connectors.factory import build

pull, push = build(connector_yaml_path)
engine = SyncEngine(push, manifest_db_path, manifest_id)

# Buffer locally (never fails due to network)
engine.enqueue(payload)

# Flush when online
stats = engine.flush(batch_size=20)
# {"attempted": 5, "succeeded": 5, "failed": 0}

# Retry errors (up to N attempts)
engine.retry_errors(max_attempts=3)

# Check status
print(engine.stats())
# {"pending": 0, "synced": 5, "error": 0}
```

The sync queue is stored in the manifest SQLite database (`sync_queue` table).

---

## Secrets Injection

Set credentials in `<CIM_LOG_DIR>/secrets/connector_creds.json`:

```json
{
  "dsn": "postgresql+psycopg2://user:pw@host/db",
  "token": "my-bearer-token",
  "base_url": "https://api.example.com"
}
```

The engine automatically injects these as `CIM_CONNECTOR_DSN`, `CIM_CONNECTOR_TOKEN`, and `CIM_CONNECTOR_BASE_URL` env vars into every Streamlit subprocess.

---

## Pull Query Requirements

The SQL pull query must return at minimum:

| Column | Required | Description |
|--------|----------|-------------|
| `id` | yes | Unique item identifier (becomes `item_id`) |
| `file_path` | yes* | Absolute local path to the image |
| `image_url` | no | Remote URL (used when file_path is absent/not local) |
| `width` | no | Image width in pixels |
| `height` | no | Image height in pixels |
| `file_hash` | no | MD5 or SHA hash for change detection |

*Either `file_path` or `image_url` must be present.

---

## Package Layout

```
cim_annotation/
├── __init__.py
├── models.py               FetchedItem, AnnotationPayload, PushResult
├── sync_engine.py          SyncEngine — offline-first buffered sync
├── label_ops.py            scan_labels, rename_label, merge_labels, delete_label
├── CONNECTOR_GUIDE.md      ← this file
└── connectors/
    ├── __init__.py
    ├── base.py             PullConnector, PushConnector ABCs
    ├── factory.py          build(connector_yaml_path) → (pull, push)
    ├── local_file.py       LocalFileConnector (default, zero-config)
    ├── sql_connector.py    SqlConnector (SQLAlchemy)
    └── rest_connector.py   RestConnector (requests)
```
