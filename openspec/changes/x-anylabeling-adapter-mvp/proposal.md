# X-AnyLabeling Adapter MVP

## Why

The platform needs to use X-AnyLabeling as an annotation editor without making X-AnyLabeling project files the source of truth. The adapter must exchange data with `annotation-core`, support LabelMe/X-AnyLabeling round trips, and prepare local project folders for users.

## What Changes

Create an X-AnyLabeling adapter MVP that:

- Exports platform canonical annotation sets to LabelMe/X-AnyLabeling-compatible files.
- Imports LabelMe/X-AnyLabeling files back into canonical annotation sets.
- Prepares X-AnyLabeling project folders from platform datasets.
- Synchronizes project/folder assets without GUI automation.
- Produces conversion reports for each import and export.
- Supports bbox, polygon, and image-level classification where the target format allows it.
- Supports COCO and YOLO detection export as derived training artifacts through the common export contract.

## MVP Scope

In scope:

- File exchange with LabelMe/X-AnyLabeling JSON.
- X-AnyLabeling project/folder preparation.
- Core-to-X-AnyLabeling sync.
- X-AnyLabeling/LabelMe-to-core import.
- COCO export.
- YOLO detection export.
- Conversion reports.
- Adapter contract tests.

Out of scope:

- GUI automation.
- Live control of X-AnyLabeling windows.
- Multi-user locking.
- YOLO segmentation export.
- Mask editing or mask conversion.
- Keypoint workflows.
- Tracking/video workflows.
- Auto-label model execution.

## Decisions

- `annotation-core` remains the only canonical truth.
- The adapter must not write directly to platform state without going through application services.
- Exported LabelMe, X-AnyLabeling, COCO, and YOLO files are artifacts.
- GUI automation, if needed later, belongs to a separate plugin or `cim-gui-mcp` style surface.

## Success Criteria

- A canonical annotation set with bbox and polygon annotations can be exported to LabelMe/X-AnyLabeling files.
- Edited LabelMe/X-AnyLabeling files can be imported back into a new canonical annotation set.
- The import/export round trip preserves supported fields.
- Unsupported or lossy fields are reported in `ConversionReport`.
- A project folder can be prepared for X-AnyLabeling from a platform dataset.
- Approved annotation sets can be exported to COCO and YOLO detection formats.
