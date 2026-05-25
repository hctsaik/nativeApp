# Phase 2 — Structured ConversionReport + Dry-run Export Spec

## Objective

Extend `ConversionReport` with structured per-item loss entries and a
`mapping_version` field. Add a `dry_run_export` service API and MCP tool so
callers can preview format losses before committing a real export.

## Requires

Phase 1 complete (FormatRegistry must exist; adapters receive format via registry).

## Files to Modify

```
annotation/core/models.py           — extend ConversionReport; add LossEntry
annotation/services.py              — add dry_run_export()
annotation/adapters/isat.py         — emit structured LossEntry for bbox approximation
annotation/adapters/coco.py         — emit structured LossEntry for RLE
annotation/adapters/yolo_detection.py    — emit LossEntry for polygon-skipped
annotation/adapters/yolo_segmentation.py — emit LossEntry for bbox-skipped
mcp/annotation_mcp/handlers.py      — add annotation_dry_run_export tool
```

## ConversionReport Extension (`annotation/core/models.py`)

Add `LossEntry` dataclass **before** `ConversionReport`:

```python
@dataclass
class LossEntry:
    asset_id: str | None        # None = dataset-level loss
    annotation_id: str | None
    loss_type: str              # "dropped" | "approximated" | "unsupported" | "truncated"
    field: str                  # e.g. "geometry", "segmentation", "rle"
    reason: str                 # human-readable explanation
    severity: str               # "warning" | "error"
```

Add 3 new fields to `ConversionReport` (append at end — backwards compatible):

```python
losses: list[LossEntry] = field(default_factory=list)
mapping_version: str | None = None   # set by orchestration when schema_mapping is used
summary: str = ""                    # auto-generated on first access
```

`summary` is computed lazily:
- `"lossless"` if `lossless=True` and `losses=[]`
- `"N warnings"` if all LossEntry are severity=warning
- `"N errors"` if any LossEntry is severity=error

## Adapter Changes

Each adapter's export path must emit `LossEntry` instead of (or in addition to)
appending to the legacy `warnings`, `dropped_fields`, `approximated_fields` lists.
Both old and new fields are populated for backwards compatibility.

| Adapter | Loss scenario | loss_type | severity |
|---|---|---|---|
| `isat.py` | bbox-only → 4-corner polygon | `approximated` | `warning` |
| `coco.py` | RLE mask encountered | `unsupported` | `warning` |
| `yolo_detection.py` | polygon exported as bbox | `approximated` | `warning` |
| `yolo_segmentation.py` | bbox-only skipped | `dropped` | `warning` |

## New Service API

```python
def dry_run_export(
    self,
    annotation_set_id: str,
    export_format: str,
    options: dict | None = None,
) -> dict:
    """
    Run export conversion without writing any files or artifacts.
    Returns the ConversionReport as a dict.
    """
```

Implementation: call `registry.get(format).adapter.export(annotation_set, schema, options)`
with a flag that suppresses file I/O. Adapters must accept `dry_run=True` in options and
skip any `write_json_artifact` / `write_conversion_report` calls.

## New MCP Tool

```
annotation_dry_run_export(annotation_set_id, format, options?) -> ConversionReport dict
```

Added in `handlers.py` alongside existing export tools.

## Tests to Add

```
tests/annotation/test_conversion_report.py
    - test_lossentry_fields
    - test_report_summary_lossless
    - test_report_summary_warnings
    - test_report_summary_errors
    - test_backwards_compat_no_losses_field   # old code that doesn't set losses still works

tests/annotation/test_dry_run_export.py
    - test_dry_run_does_not_write_files
    - test_dry_run_isat_reports_bbox_approximation
    - test_dry_run_coco_reports_rle_unsupported
    - test_dry_run_yolo_det_reports_polygon_dropped
    - test_dry_run_yolo_seg_reports_bbox_dropped
    - test_dry_run_lossless_for_labelme
```

## Acceptance Criteria

- [ ] `ConversionReport` serialises/deserialises with all 12 fields (9 old + 3 new)
- [ ] Old code that constructs `ConversionReport()` without new fields still works
- [ ] `dry_run_export` writes zero files
- [ ] ISAT bbox export appears as `approximated` LossEntry
- [ ] COCO RLE appears as `unsupported` LossEntry
- [ ] MCP tool `annotation_dry_run_export` callable and returns report dict
- [ ] All existing export tests still pass (no regressions)
