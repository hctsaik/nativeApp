# Annotation Common Component

## Why

The platform needs a reusable annotation foundation that can support many future image tasks without being tied to the first animal-image use case or to X-AnyLabeling internals.

The canonical source of truth must live in the platform, not in LabelMe JSON, X-AnyLabeling project files, COCO, or YOLO exports. External formats are adapters or derived artifacts.

## What Changes

Create an `annotation-core` common component with:

- Canonical data model for datasets, image assets, label schemas, annotation sets, annotations, geometry, tasks, jobs, reviews, exports, artifacts, validation, and audit records.
- Local MVP storage using a workspace folder plus SQLite catalog.
- Storage ports for future replacement by other metadata and artifact backends.
- Schema-driven labels and attributes instead of unconstrained free-form annotation fields.
- Basic review and approval workflow.
- Export preview support for draft annotations and publish/training export support for approved annotations.
- Conversion reporting for lossy adapters and export formats.
- Generic `annotation_*` MCP contract, separate from GUI automation MCP.

## MVP Scope

In scope:

- Image assets.
- Bounding boxes.
- Polygons.
- Image-level classification.
- Label schema and attribute schema.
- Local workspace artifact layout.
- SQLite catalog.
- Annotation set versioning and audit trail.
- Basic validation.
- Basic review and approval.
- Generic annotation MCP resources and tool contract.

Out of scope for MVP:

- Multi-user collaboration, lock management, and assignment queues.
- Realtime collaborative editing.
- Mask editing and mask conversion.
- Keypoint/skeleton workflows.
- Tracking/video annotation workflows.
- OCR reading order and table structure.
- Medical imaging compliance workflows.
- OAuth/SSO and complex role policy.
- GUI automation.

## Decisions

- `annotation-core` is the only canonical truth.
- X-AnyLabeling, LabelMe, COCO, and YOLO are adapters or export artifacts.
- The MVP does not need multi-user collaboration.
- Review and approval are required.
- Domain attributes must be constrained by schema definitions.
- The first implementation uses local workspace storage and SQLite, but core interfaces must not depend on those implementations.

## Success Criteria

- A dataset can be created and populated with image assets.
- A label schema can define bbox, polygon, and image classification tasks with required attributes.
- An annotation set can be created, validated, submitted, reviewed, approved, rejected, or sent back for changes.
- Draft annotations can be exported for preview.
- Approved annotations can be exported for training or publish workflows.
- Validation and conversion reports use stable, structured fields.
- The same core model can support animal images, defect inspection, OCR layout, and product inspection by adding domain schemas and adapters rather than changing core contracts.
