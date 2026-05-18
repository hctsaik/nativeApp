# Annotation Common Component Design

## Architecture

The platform annotation capability is split into four layers:

```text
annotation-core
  Canonical model, validation, state transitions, versioning, audit,
  storage ports, artifact references.

annotation-adapters
  LabelMe, X-AnyLabeling, COCO, YOLO detection, and future adapters.

annotation-domains
  Animal, defect inspection, OCR layout, product inspection, and future
  domain schema packs.

annotation-plugins
  MCP tools/resources, Streamlit or portal integrations, review/export
  workflows, model runners.
```

Dependency direction:

```text
plugin -> domain -> core
adapter -> core
plugin -> adapter
core -> no platform-specific dependency
```

`cim-gui-mcp` remains a GUI automation and E2E surface. The annotation MCP surface is a data and workflow API and must not depend on GUI selectors or browser automation.

## Core Model

```text
Dataset
- id
- name
- root_uri
- state
- metadata
- created_at
- updated_at

ImageAsset
- id
- dataset_id
- uri
- width
- height
- checksum
- media_type: image
- metadata
- created_at

LabelSchema
- id
- name
- version
- task_types: detection | segmentation | classification
- labels: LabelDef[]
- attribute_schema: AttributeDef[]
- geometry_constraints

LabelDef
- id
- name
- color
- allowed_geometry_types
- required_attributes
- domain_attributes

AnnotationSet
- id
- dataset_id
- schema_id
- source: human | model | imported | fused
- state: draft | submitted | approved | changes_requested | rejected | deprecated
- version
- created_by
- created_at
- updated_at
- provenance

Annotation
- id
- annotation_set_id
- asset_id
- label_id
- geometry: Geometry | null
- classification: ClassificationValue[] | null
- confidence
- source: human | model | imported | rule
- attributes
- review_status
- provenance
- version

Task
- id
- dataset_id
- schema_id
- annotation_set_id
- state
- task_type
- metadata

Job
- id
- kind
- state: queued | running | succeeded | partial_success | failed | canceled
- total
- succeeded
- failed
- artifact_refs
- report_ref

ArtifactRef
- artifact_id
- uri
- media_type
- size_bytes
- sha256
- storage_backend
- schema_version
```

## Geometry

Geometry is a discriminated union. The MVP implements only bbox, polygon, and classification. Other types can be reserved as schema enum values but return `UNSUPPORTED_GEOMETRY` until implemented.

```text
BBox
- type: bbox
- coordinate_space: pixel | normalized
- x
- y
- width
- height

Polygon
- type: polygon
- coordinate_space: pixel | normalized
- rings
- closed

Classification
- geometry: null
- classification: labels/probabilities
```

Reserved future geometry types:

```text
rotated_bbox
polyline
point
keypoints
mask_ref
text_region
relation
```

Large binary data, masks, render outputs, and export files must be stored as artifacts and referenced by `ArtifactRef`.

## Storage

MVP storage:

```text
workspace/
  catalog.sqlite
  datasets/{dataset_id}/
    assets/
      originals/
      derivatives/
    annotations/{annotation_set_id}/
      canonical.json
      manifest.json
    manifests/
    artifacts/
    exports/
```

Core depends on ports, not implementation paths:

```text
MetadataStore
- datasets
- assets
- schemas
- annotation_sets
- annotations
- tasks
- jobs
- reviews
- audit_events
- artifact_index

ArtifactStore
- put
- get
- exists
- checksum
- list
- archive
```

## Review And Approval

The MVP does not require multi-user collaboration, but review and approval are required.

Annotation set states:

```text
draft -> submitted
submitted -> approved
submitted -> changes_requested -> draft
submitted -> rejected
approved -> deprecated
```

Approval decisions are immutable records:

```text
ReviewDecision
- id
- target_type: annotation_set | task | export
- target_id
- target_version
- decision: approved | rejected | changes_requested
- actor_id
- comment
- decided_at
```

`exported` is not an annotation set state. Exports are separate derived artifacts and can be created multiple times from the same approved annotation set.

## Validation

Validation returns structured issues:

```text
ValidationIssue
- severity: error | warning | info
- code
- message
- annotation_id
- asset_id
- field_path
- rule_id
- suggested_fix
```

Core MVP validation:

- Schema exists and versions match.
- Label is defined in the schema.
- Geometry type is allowed for the label.
- Coordinates are finite.
- BBox width and height are positive.
- BBox and polygon coordinates are within image bounds unless schema allows overflow.
- Polygon has at least three points and non-zero area.
- Required attributes are present and type-valid.
- Image classification follows single-label or multi-label constraints.
- Approved annotation sets cannot be overwritten by import or model output.

Domain validation is supplied by domain schema packs and plugins.

## MCP Surface

Generic resources:

```text
annotation://datasets/{dataset_id}
annotation://assets/{asset_id}
annotation://schemas/{schema_id}
annotation://tasks/{task_id}
annotation://annotation-sets/{annotation_set_id}
annotation://reviews/{review_id}
annotation://jobs/{job_id}
annotation://exports/{export_id}
annotation://reports/{report_id}
```

Generic tools:

```text
annotation_create_dataset
annotation_list_datasets
annotation_ingest_assets
annotation_create_schema
annotation_get_schema
annotation_create_task
annotation_get_task
annotation_list_tasks
annotation_get_asset_annotations
annotation_upsert_annotations
annotation_validate_set
annotation_submit_for_review
annotation_review_task
annotation_create_export
annotation_get_export
annotation_get_job_status
annotation_cancel_job
```

Domain-specific tools may exist as thin wrappers, but they must call the same common application services.

## Error Contract

```json
{
  "ok": false,
  "error": {
    "code": "CONFLICT",
    "message": "Annotation set version conflict.",
    "details": {
      "annotation_set_id": "aset_001",
      "expected_version": 3,
      "actual_version": 4
    },
    "retryable": false
  }
}
```

Required error codes:

```text
VALIDATION_ERROR
NOT_FOUND
CONFLICT
PERMISSION_DENIED
UNSUPPORTED_FORMAT
UNSUPPORTED_GEOMETRY
RESOURCE_UNREADABLE
EXPORT_FAILED
PARTIAL_SUCCESS
```

## Export Rules

- Draft annotation sets may be exported for preview.
- Approved annotation sets may be exported for training or publish workflows.
- Export artifacts must include a conversion report.
- Export artifacts must not become canonical truth.

Conversion report:

```text
ConversionReport
- lossless
- dropped_fields
- approximated_fields
- coordinate_transform
- class_mapping
- warnings
- source_schema_version
- target_format
- target_format_version
```
