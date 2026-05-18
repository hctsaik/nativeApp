# Tasks: X-AnyLabeling Adapter MVP

## Phase 0 - Adapter Contract

- [x] Confirm adapter depends on `annotation-core` contracts.
- [x] Confirm LabelMe/X-AnyLabeling JSON as the file exchange format.
- [x] Confirm project/folder sync without GUI automation.
- [x] Confirm COCO and YOLO detection exports only.
- [x] Confirm conversion reports are required for all import/export jobs.

## Phase 1 - Project Preparation

- [x] Implement `XAnyLabelingProjectAdapter`.
- [x] Prepare project folder layout.
- [x] Sync image assets into the project folder.
- [x] Write label/class configuration from `LabelSchema`.
- [x] Write project manifest.
- [x] Add tests for deterministic project generation.

## Phase 2 - LabelMe / X-AnyLabeling Round Trip

- [x] Implement canonical-to-LabelMe export for bbox.
- [x] Implement canonical-to-LabelMe export for polygon.
- [x] Implement canonical-to-LabelMe export for image-level classification where supported.
- [x] Implement LabelMe-to-canonical import for bbox.
- [x] Implement LabelMe-to-canonical import for polygon.
- [x] Implement LabelMe-to-canonical import for image-level classification where supported.
- [x] Preserve supported metadata where possible.
- [x] Report unsupported and lossy fields.
- [x] Add round-trip fixture tests.

## Phase 3 - Training Exports

- [x] Implement COCO export for bbox.
- [x] Implement COCO export for polygon where supported by the selected COCO task.
- [x] Implement YOLO detection export for bbox.
- [x] Write deterministic class mapping.
- [x] Write export manifest for YOLO detection.
- [x] Write conversion report.
- [x] Add COCO fixture tests.
- [x] Add YOLO detection fixture tests.

## Phase 4 - Application Service Integration

- [x] Add `prepare_xanylabeling_project`.
- [x] Add `import_xanylabeling_annotations`.
- [x] Add `export_labelme`.
- [x] Add `export_coco`.
- [x] Add `export_yolo_detection`.
- [x] Ensure imports create a new annotation set version or derived annotation set.
- [x] Ensure approved annotation sets cannot be overwritten by adapter import.

## Phase 5 - MCP Integration

- [x] Add adapter tools under the generic annotation MCP surface.
- [x] Add `annotation_prepare_xanylabeling_project`.
- [x] Add `annotation_detect_xanylabeling`.
- [x] Add `annotation_launch_xanylabeling_project`.
- [x] Add `annotation_import_xanylabeling`.
- [x] Add exports through `annotation_create_export`.
- [x] Add MCP handler tests.

## Phase 6 - Documentation

- [x] Document project folder layout.
- [x] Document LabelMe/X-AnyLabeling supported fields.
- [x] Document lossy field behavior.
- [x] Document conversion report examples.
- [x] Document COCO and YOLO detection export rules.

## Acceptance

- [x] A platform dataset can be prepared as an X-AnyLabeling project folder.
- [x] BBox annotations round-trip between canonical and LabelMe/X-AnyLabeling files.
- [x] Polygon annotations round-trip between canonical and LabelMe/X-AnyLabeling files.
- [x] Image-level classification is handled or explicitly reported as unsupported by the selected target format.
- [x] COCO export can be generated from approved annotation sets.
- [x] YOLO detection export can be generated from approved annotation sets.
- [x] Every import/export creates a manifest and conversion report.
- [x] No GUI automation is required for the MVP adapter.
