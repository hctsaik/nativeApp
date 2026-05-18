# X-AnyLabeling Adapter MVP Design

## Relationship To Annotation Core

The adapter is not a domain model and not the canonical source of truth.

```text
annotation-core canonical set
        |
        v
XAnyLabelingAdapter
        |
        v
LabelMe / X-AnyLabeling project files
```

Imports create or update canonical annotation sets through application services. Exports create artifacts and manifests.

## Adapter Interfaces

```text
XAnyLabelingProjectAdapter
- prepare_project(dataset_id, schema_id, asset_ids, output_uri)
- sync_assets(dataset_id, asset_ids, output_uri)
- write_label_config(schema_id, output_uri)

LabelMeAdapter
- export_annotation_set(annotation_set_id, output_uri)
- import_annotations(dataset_id, schema_id, input_uri)

TrainingExportAdapter
- export_coco(annotation_set_id, output_uri, include_states)
- export_yolo_detection(annotation_set_id, output_uri, include_states)
```

Every adapter operation returns:

```text
AdapterResult
- artifact_refs
- conversion_report
- job_id
- warnings
```

## Project Folder Layout

```text
external/
  x-anylabeling/{job_id}/
    project/
      images/
      labels/
      classes.txt
      manifest.json
    imports/
    exports/
```

The project manifest records:

```text
dataset_id
schema_id
annotation_set_id
adapter_version
x_anylabeling_version
source_asset_checksums
generated_at
```

## Supported Canonical Fields

Supported for MVP round trip:

- `asset_id`
- `label_id`
- `geometry.type = bbox`
- `geometry.type = polygon`
- `attributes` when representable in LabelMe/X-AnyLabeling metadata.
- `source`
- `confidence`
- `annotation_id` through metadata when possible.

Supported with lossiness:

- Review state.
- Annotation set state.
- Schema version.
- Provenance.
- Audit records.

Unsupported for MVP:

- Masks.
- Keypoints.
- Tracking fields.
- OCR hierarchy.
- Relations.
- Large artifact references inside an annotation shape.

Unsupported or lossy fields must be listed in the conversion report.

## Conversion Report

```text
ConversionReport
- lossless
- dropped_fields
- approximated_fields
- unsupported_annotations
- coordinate_transform
- class_mapping
- warnings
- source_format_version
- target_format_version
```

YOLO detection export is expected to be lossy because it keeps class and normalized bbox only.

COCO export may preserve bbox and polygon, but review state, schema details, and arbitrary attributes may require extension fields or be reported as dropped.

## Sync Direction

MVP supports both directions:

```text
annotation-core -> X-AnyLabeling project
X-AnyLabeling / LabelMe JSON -> annotation-core
```

Conflict handling is simple because MVP has no multi-user collaboration. Imports should create a new annotation set version or new derived annotation set rather than silently overwriting approved canonical data.

## Export Rules

- Draft annotation sets can be exported to LabelMe/X-AnyLabeling for editing and to preview exports.
- Approved annotation sets can be exported to COCO or YOLO detection for training/publish workflows.
- Every export must write a manifest and conversion report.

## Testing Strategy

Adapter contract fixtures:

- Empty image with no annotations.
- Single bbox.
- Multiple bboxes.
- Single polygon.
- Multiple polygons.
- Image-level classification.
- Required attributes.
- Unsupported geometry fixture.

Round-trip checks:

- Canonical to LabelMe/X-AnyLabeling to canonical.
- Label IDs remain mapped.
- Coordinates remain within acceptable tolerance.
- Unsupported fields are reported, not silently ignored.

Training export checks:

- COCO category IDs and annotation IDs are stable.
- YOLO class index mapping is deterministic.
- YOLO bbox normalization is correct.
- Export manifests include source annotation set ID and checksum.
