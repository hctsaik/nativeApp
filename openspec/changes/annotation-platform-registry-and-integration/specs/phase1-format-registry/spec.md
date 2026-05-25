# Phase 1 — FormatRegistry Spec

## Objective

Replace the four `if/elif` format dispatch blocks in `AnnotationService` with a
pluggable `FormatRegistry`. No new features; existing behaviour preserved exactly.

## Files to Create

```
annotation/formats/__init__.py
annotation/formats/contracts.py
annotation/formats/registry.py
annotation/formats/builtins.py
```

## Files to Modify

```
annotation/services.py          — remove if/elif dispatch, read from registry
annotation/core/models.py       — add FormatCapabilities to exports (no field changes)
```

## Contracts (`contracts.py`)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Protocol

@dataclass
class FormatCapabilities:
    can_import: bool
    can_export: bool
    requires_asset: bool        # COCO → False; all others → True
    supports_polygon: bool
    supports_bbox: bool
    supports_classification: bool
    lossless_roundtrip: bool    # True: labelme, x-anylabeling only

@dataclass
class FormatDescriptor:
    format_id: str              # canonical ID e.g. "x-anylabeling"
    display_name: str
    aliases: list[str]          # e.g. ["xanylabeling", "x_anylabeling"]
    capabilities: FormatCapabilities

class FormatAdapter(Protocol):
    def import_file(self, path: str, schema, asset_id: str | None) -> tuple[list, ConversionReport]: ...
    def import_dir(self, path: str, schema) -> tuple[list, ConversionReport]: ...
    def export(self, annotation_set, schema, options: dict) -> tuple[Any, ConversionReport]: ...
    def import_project_labels(self, path: str) -> list[str]: ...
```

## Registry (`registry.py`)

```python
class FormatRegistry:
    def register(self, descriptor: FormatDescriptor, adapter: FormatAdapter) -> None: ...
    def get(self, format_id: str) -> tuple[FormatDescriptor, FormatAdapter]:
        """Normalises aliases. Raises ValueError on unknown format."""
    def list_supported(self) -> list[dict]:
        """Returns same shape as current supported_annotation_formats()."""
    def normalize(self, format_id: str) -> str:
        """Replaces _normalize_format() in services.py."""

def get_format_registry() -> FormatRegistry: ...  # module-level singleton
```

## Builtins (`builtins.py`)

Registers all 6 existing adapters. Called once at module import:

| format_id | aliases | requires_asset | lossless_roundtrip |
|---|---|---|---|
| `labelme` | `label-me` | True | True |
| `x-anylabeling` | `xanylabeling`, `x_anylabeling` | True | True |
| `isat` | — | True | False |
| `coco` | `coco-json` | **False** | False |
| `yolo-detection` | `yolo_detection`, `yolo-det` | True | False |
| `yolo-segmentation` | `yolo_segmentation`, `yolo-seg`, `yolo_segment` | True | False |

## Services.py Changes

### Remove (lines 6–13)
All 10 direct adapter function imports. Replace with:
```python
from annotation.formats.registry import get_format_registry
```

### `supported_annotation_formats()` (lines 331–339)
Replace hardcoded list:
```python
def supported_annotation_formats(self) -> list[dict]:
    return get_format_registry().list_supported()
```

### `import_annotations()` (lines 276–290)
Before dispatch: `caps = registry.get(fmt)[0].capabilities`
Replace `if fmt == "coco": asset = None` with `if not caps.requires_asset: asset = None`
Then: `adapter.import_file(path, schema, asset_id)`

### `import_project_labels()` (lines 305–322)
Replace if/elif with: `registry.get(fmt)[1].import_project_labels(path)`

### `create_export()` (lines 359–370)
Replace if/elif with: `registry.get(normalized_format)[1].export(annotation_set, schema, options)`

### `_normalize_format()` (lines 462–475)
Delete. All callers replaced by `registry.normalize(fmt)`.

### `prepare_labeling_project()` (lines 222–227)
**Do not touch.** This dispatches on labeling tool (not format). Belongs to Phase 3.

## Tests to Add (before implementation)

```
tests/annotation/test_format_registry.py
    - test_register_and_get_by_id
    - test_get_by_alias_normalizes
    - test_unknown_format_raises_value_error
    - test_coco_requires_asset_false
    - test_list_supported_shape_matches_legacy
    - test_all_builtins_registered
```

Existing tests that must still pass:
```
tests/annotation/test_services.py   — all existing test_import_* / test_export_* cases
tests/annotation/test_adapters.py   — no changes expected
```

## Acceptance Criteria

- [ ] `supported_annotation_formats()` returns identical list shape to pre-Phase-1
- [ ] All 6 formats importable and exportable via registry dispatch
- [ ] `_normalize_format()` deleted from services.py; aliases work via registry
- [ ] COCO import works without `asset_id` (via `requires_asset=False`)
- [ ] All existing MCP tool calls succeed with unchanged signatures
- [ ] `npm run test:python` fully green
