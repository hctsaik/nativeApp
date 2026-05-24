# Multi Labeling Tool And Format Support

## Why

The annotation platform currently treats X-AnyLabeling as the main external
labeling workflow, while most file conversion logic is LabelMe-compatible JSON
under the hood. Users need the same workflow to support multiple labeling tools
and mainstream annotation formats, including LabelMe, X-AnyLabeling, ISAT, COCO,
YOLO detection, and YOLO segmentation.

## What Changes

- Add an explicit annotation format dispatch layer in the annotation service.
- Keep canonical annotation-core models as the source of truth.
- Add native ISAT JSON import/export.
- Add COCO, YOLO detection, and YOLO segmentation import support in addition
  to existing COCO/YOLO detection export and new YOLO segmentation export.
- Preserve LabelMe and X-AnyLabeling compatibility, including X-AnyLabeling's
  four-point rectangle representation.
- Prepare project folders for tool-specific workflows without making GUI state
  canonical.
- Expose the supported format list to callers so UI, MCP, and modules can avoid
  hard-coded one-tool assumptions.

## Impact

- Affected code:
  - `sidecar/python-engine/annotation/adapters/*`
  - `sidecar/python-engine/annotation/services.py`
  - `sidecar/python-engine/scripts/module_006`
  - `sidecar/python-engine/scripts/module_008`
  - `sidecar/python-engine/scripts/module_009`
  - `sidecar/python-engine/scripts/module_012`
  - `mcp/annotation_mcp/*`
- Affected tests:
  - `sidecar/python-engine/tests/annotation/test_adapters.py`
  - `sidecar/python-engine/tests/annotation/test_services.py`
