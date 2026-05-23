# Annotation Workflow Extensions Design

## Architecture Overview

The extension introduces a three-layer model on top of the existing
split-tool module architecture:

```text
UI Layer (Streamlit module templates)
  module_010 ~ module_018
  → reads params from input page, calls process.py, renders output page
  → unchanged modules continue to work; new modules follow same pattern

Core Logic Layer  (cim_annotation/)
  label_ops.py     → scan / rename / merge / delete labels across JSON files
  sync_engine.py   → offline-first sync loop, conflict detection
  models.py        → FetchedItem, AnnotationPayload, PushResult dataclasses

Transport Layer  (cim_annotation/connectors/)
  base.py          → PullConnector, PushConnector ABC
  local_file.py    → default, zero-config, backwards-compatible
  sql_connector.py → SQLAlchemy (PostgreSQL / MySQL / SQLite remote)
  rest_connector.py→ requests (HTTP REST, streaming download, Bearer token)
  factory.py       → ConnectorFactory: loads built-ins or custom via importlib
```

Dependency direction:

```text
module_*.py → ConnectorFactory → concrete connector → platform infra
module_*.py → label_ops.py
module_*.py → sync_engine.py
connector   → models.py
core        → no Streamlit or engine.py dependency
```

## DataConnector Interface

### PullConnector

```python
# cim_annotation/connectors/base.py

@dataclass
class FetchedItem:
    item_id:    str
    file_path:  str        # local abs path after resolve_image(); empty until then
    image_url:  str | None # populated by URL connectors; None for shared-mount
    width:      int | None
    height:     int | None
    file_hash:  str | None # remote md5/sha256 for cache validation
    metadata:   dict       # arbitrary pass-through (remote_id, tags, ...)

class PullConnector(ABC):
    @abstractmethod
    def fetch_page(self, offset: int, limit: int) -> list[FetchedItem]: ...

    @abstractmethod
    def resolve_image(self, item: FetchedItem, local_dir: Path) -> Path:
        """
        Shared-mount connector: stat() + symlink, zero copy.
        REST connector: streaming GET, skip if hash matches cached file.
        """

    def fetch_all(self, local_dir: Path, page_size: int = 200) -> Iterator[FetchedItem]:
        offset = 0
        while True:
            page = self.fetch_page(offset, page_size)
            if not page:
                break
            for item in page:
                item.file_path = str(self.resolve_image(item, local_dir))
                yield item
            offset += len(page)
```

### PushConnector

```python
@dataclass
class AnnotationPayload:
    item_id:       str
    remote_id:     str          # original PK from FetchedItem.metadata["remote_id"]
    image_path:    str          # basename only
    image_width:   int
    image_height:  int
    shapes:        list[dict]   # X-AnyLabeling shape objects verbatim
    classification: str | None
    confidence:    float | None
    annotator:     str          # "manual" | "model" | "xanylabeling"
    annotated_at:  str          # ISO-8601 UTC

@dataclass
class PushResult:
    item_id:    str
    success:    bool
    remote_ref: str | None  # server-assigned id; used for idempotent retry
    error:      str | None

class PushConnector(ABC):
    @abstractmethod
    def push_batch(self, payloads: list[AnnotationPayload]) -> list[PushResult]:
        """
        Partial failure: returns PushResult per item.
        Failed items remain in sync_queue for retry.
        """

    @abstractmethod
    def check_remote_version(self, item_ids: list[str]) -> dict[str, str]:
        """Return {item_id: remote_updated_at} for conflict detection."""
```

`LocalFileConnector` implements both ABCs. Its `push_batch` writes
`AnnotationPayload.shapes` as X-AnyLabeling JSON files alongside the images,
identical to the current module behavior.

## ConnectorFactory

```python
# cim_annotation/connectors/factory.py

def build(connector_yaml_path: str | None = None) -> tuple[PullConnector, PushConnector]:
    """
    Returns (pull, push) connector pair.
    Falls back to LocalFileConnector when connector_yaml_path is None or absent.
    """
    if not connector_yaml_path or not Path(connector_yaml_path).exists():
        c = LocalFileConnector()
        return c, c

    cfg = yaml.safe_load(Path(connector_yaml_path).read_text(encoding="utf-8"))
    t = cfg["connector"]["type"]

    if t == "local_file":
        c = LocalFileConnector(**cfg["connector"].get("local_file", {}))
        return c, c
    if t == "sql":
        dsn = os.environ[cfg["connector"]["sql"]["dsn_env"]]
        image_root = Path(cfg["connector"]["sql"].get("image_root", ""))
        c = SqlConnector(dsn, image_root or None)
        return c, c
    if t == "rest":
        base_url = os.environ[cfg["connector"]["rest"]["base_url_env"]]
        token = os.environ.get(cfg["connector"]["rest"].get("token_env", ""), "")
        session = _make_session(token)
        c = RestConnector(base_url, session)
        return c, c
    if t == "custom":
        mod = importlib.import_module(cfg["connector"]["custom"]["module"])
        cls = getattr(mod, cfg["connector"]["custom"]["class"])
        c = cls(cfg["connector"]["custom"].get("config", {}))
        return c, c

    raise ValueError(f"Unknown connector type: {t}")
```

## connector.yaml Schema

Place `connector.yaml` alongside any module's `plugin.yaml`. Engine injects
`CIM_CONNECTOR_CONFIG` env var pointing to this file before spawning Streamlit.

```yaml
connector:
  type: local_file   # local_file | sql | rest | custom

  local_file:
    image_root: ""   # empty = use source_path from shared.json

  sql:
    dsn_env: CIM_CONNECTOR_DSN           # read from env; never hardcoded
    image_root: "/mnt/nas/images"        # shared filesystem mount
    items_table: annotation_items
    results_table: annotation_results

  rest:
    base_url_env: CIM_CONNECTOR_BASE_URL
    token_env: CIM_CONNECTOR_TOKEN       # Bearer token; omit if no auth
    # Expected endpoints:
    # GET  /api/v1/images?offset=N&limit=N
    # POST /api/v1/annotations/batch
    # POST /api/v1/annotations/versions

  custom:
    module: connectors.my_org_connector  # importlib path relative to module root
    class: MyConnector
    config: {}
```

## Credential Injection

`engine.py _make_env()` already injects `CIM_*` env vars per subprocess.
Extend it to read `secrets/connector_creds.json` from `CIM_LOG_DIR`:

```python
# engine.py _make_env() addition
secrets_path = self._cim_log_dir / "secrets" / "connector_creds.json"
if secrets_path.exists():
    creds = json.loads(secrets_path.read_text(encoding="utf-8"))
    env["CIM_CONNECTOR_DSN"]      = creds.get("dsn", "")
    env["CIM_CONNECTOR_TOKEN"]    = creds.get("token", "")
    env["CIM_CONNECTOR_BASE_URL"] = creds.get("base_url", "")
```

The Streamlit input page shows only a connection health indicator (one
`fetch_page(0, 1)` call). Raw DSN strings and tokens are never rendered in the UI.

## Offline-First Sync

Add one table to `manifest.sqlite` via `_manifest_db.py`:

```sql
CREATE TABLE IF NOT EXISTS sync_queue (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id          TEXT NOT NULL,
    manifest_id      TEXT NOT NULL,
    local_updated_at TEXT NOT NULL,
    remote_ref       TEXT,       -- filled after first successful push (idempotency key)
    status           TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'synced', 'conflict'))
);
```

Sync flow:

```text
1. X-AnyLabeling save → mtime change detected by 012_output.py _incremental_refresh
2. INSERT INTO sync_queue (item_id, manifest_id, local_updated_at, status='pending')
3. SyncEngine.run_once():
   a. SELECT pending items from sync_queue
   b. push_connector.check_remote_version(item_ids) → {item_id: remote_updated_at}
   c. Conflict: remote_updated_at > session_start_at → status='conflict', surface in UI
   d. Non-conflict: push_connector.push_batch(payloads) → PushResult[]
   e. Success: UPDATE sync_queue SET status='synced', remote_ref=... WHERE item_id=...
   f. Failure: item stays 'pending'; retry on next run
4. ConnectError → all items stay 'pending'; silent until next online attempt
```

## SqlConnector Design

Expected remote schema:

```sql
-- Pull source
CREATE TABLE annotation_items (
    id        SERIAL PRIMARY KEY,
    file_path TEXT NOT NULL,      -- relative to image_root
    width     INTEGER,
    height    INTEGER,
    md5       TEXT
);

-- Push target
CREATE TABLE annotation_results (
    id             SERIAL PRIMARY KEY,
    image_id       INTEGER NOT NULL REFERENCES annotation_items(id),
    shapes         JSONB,
    classification TEXT,
    confidence     FLOAT,
    annotator      TEXT,
    annotated_at   TIMESTAMPTZ,
    updated_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (image_id)
);
```

Push uses `INSERT ... ON CONFLICT (image_id) DO UPDATE` (PostgreSQL upsert).
`remote_ref` in `sync_queue` stores the returned `annotation_results.id`.

## RestConnector Design

Expected API surface (operator-implemented):

```text
GET  /api/v1/images?offset=N&limit=N
     → {"items": [{id, url, width, height, md5}], "total": N}

POST /api/v1/annotations/batch
     body: {"annotations": [{image_id, shapes, classification, confidence, annotator, annotated_at}]}
     → {"results": [{image_id, annotation_id, status, error}]}

POST /api/v1/annotations/versions
     body: {"image_ids": [...]}
     → {"versions": {image_id: updated_at}}
```

Image download: streaming GET to local `{CIM_LOG_DIR}/images/{manifest_id}/`,
skip if file exists and md5 hash matches. base64 encoding is not supported.

## module_017 Label Manager

```text
plugin.yaml:
  id: module_017
  runner: cv_framework
  input_file:  017_input.py
  output_file: 017_output.py
  process_file: 017_process.py
```

### Process (017_process.py)

Core logic lives in `cim_annotation/label_ops.py`:

```python
def scan_labels(items: list[dict]) -> dict[str, list[str]]:
    """Return {label: [file_path, ...]} for all shapes + flags.classification."""

def find_near_duplicates(labels: list[str], threshold: float = 0.8) -> list[tuple[str, str, float]]:
    """Return pairs with SequenceMatcher ratio > threshold and < 1.0."""

def rename_label(items: list[dict], old: str, new: str) -> int:
    """Atomic rename across all JSON files. Returns count of modified files."""

def merge_labels(items: list[dict], sources: list[str], target: str) -> int:
    """Call rename_label sequentially. Returns total files modified."""

def delete_label(items: list[dict], label: str) -> int:
    """Remove all shapes with label and clear flags.classification == label."""
```

Atomic write pattern (all operations):

```python
tmp = path.with_suffix(".tmp")
tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
tmp.replace(path)   # os.replace: atomic on same filesystem
```

### Output UI (017_output.py)

```text
Left column (40%):
  st.text_input("Filter labels")
  st.dataframe: label | shapes count | files count
  ⚠️ near-duplicate banner if pairs detected

Right column (60%) — three tabs:
  Rename:
    st.text_input("New name")
    st.warning("Will affect N files") [Preview] then [Confirm ✓]

  Merge:
    st.multiselect("Labels to merge")
    st.selectbox("Merge into")
    [Preview] then [Confirm ✓]

  Delete:
    st.warning("Will remove label from N files")
    st.expander("Affected files") → list
    [Confirm Delete]
```

All destructive actions require two-step confirmation before calling process.

## module_018 Review Gallery

```text
plugin.yaml:
  id: module_018
  runner: cv_framework
  input_file:  018_input.py
  output_file: 018_output.py
  process_file: 018_process.py
```

### Overlay Rendering

PIL ImageDraw cached by `(image_path, annotation_path, mtime)`:

```python
@st.cache_data(hash_funcs={Path: lambda p: p.stat().st_mtime if p.exists() else 0})
def _render_thumb(img_path: Path, ann_path: Path, size: int = 300) -> bytes:
    img = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    if ann_path.exists():
        shapes = json.loads(ann_path.read_text(encoding="utf-8")).get("shapes", [])
        for s in shapes:
            if s["shape_type"] == "rectangle":
                pts = s["points"]
                draw.rectangle([pts[0], pts[2]], outline="red", width=2)
                draw.text(pts[0], s.get("label", ""), fill="red")
    img.thumbnail((size, size))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return buf.getvalue()
```

### Output UI (018_output.py)

```text
Layout: left sidebar (25%) | gallery grid (75%)

Filter sidebar:
  st.multiselect("Labels")
  st.selectbox("Status", ["all", "annotated", "unannotated"])
  st.slider("Min bbox count", 0, 50)
  [Apply Filters]

Gallery grid (PAGE_SIZE = 30):
  st.columns(3) per row
  Each cell: st.image(thumb_bytes) + caption: filename | N shapes
  [← Prev page] [Page X / N] [Next page →]

Click thumbnail → detail view replaces grid:
  Full-size image with overlays (max 800px wide)
  st.dataframe: shapes list (label, shape_type, area)
  st.button("Open in X-AnyLabeling") → subprocess.Popen([xany_exe, img_path])
  st.button("Flag for re-annotation 🚩") → writes sidecar .flag file
  [← Back to gallery]
```

Flagged items display a yellow border on the thumbnail via PIL before caching.

## Pre-export Validation (module_014 addition)

Before any export format is written, run `_validate_pre_export(items, shapes_map, classifications)`:

```python
@dataclass
class ValidationIssue:
    severity: str    # "error" | "warning"
    code:     str
    item_id:  str
    message:  str

def _validate_pre_export(items, shapes_map, classifications) -> list[ValidationIssue]:
    issues = []
    for it in items:
        iid = it["item_id"]
        shapes = shapes_map.get(iid, [])
        clf = classifications.get(iid, "")

        if not shapes and not clf:
            issues.append(ValidationIssue("warning", "NO_ANNOTATION", iid,
                          "Image has no bbox shapes or classification"))

        for s in shapes:
            w = s["x2"] - s["x1"]; h = s["y2"] - s["y1"]
            if w * h < MIN_BBOX_AREA:
                issues.append(ValidationIssue("warning", "TINY_BBOX", iid,
                              f"Bbox area {w*h:.0f}px² is below threshold {MIN_BBOX_AREA}px²"))

        if shapes and not clf and classifications:  # clf task was active
            issues.append(ValidationIssue("warning", "MISSING_CLASSIFICATION", iid,
                          "Image has bbox annotations but no classification"))
    return issues
```

Output page shows issues in a collapsible `st.expander` before rendering export
paths. Errors block export. Warnings show with an override checkbox.

## cim_annotation/ Submodule Layout

```text
sidecar/python-engine/
  cim_annotation/                ← candidate git submodule boundary
    __init__.py
    models.py                    ← FetchedItem, AnnotationPayload, PushResult
    label_ops.py                 ← scan, rename, merge, delete, near_dupes
    sync_engine.py               ← SyncEngine, sync_queue helpers
    connectors/
      __init__.py
      base.py                    ← PullConnector, PushConnector ABC
      local_file.py
      sql_connector.py
      rest_connector.py
      factory.py
  scripts/
    module_010 ~ module_018/     ← UI templates (stay in consumer repo)
    shared/
      _manifest_db.py            ← add sync_queue DDL
```

When a second team adopts this framework:

```bash
# In their repo
git submodule add https://github.com/your-org/cim-annotation sidecar/python-engine/cim_annotation
# Copy module templates they need
cp -r ../nativeApp/scripts/module_01{0,2,3,4,5,6,7,8} ./scripts/
# Write their connector.yaml
# Write their connector_creds.json (gitignored)
```

Core fixes in the submodule flow in via `git submodule update --remote`.
Module template customizations stay in the consumer repo and never conflict.
