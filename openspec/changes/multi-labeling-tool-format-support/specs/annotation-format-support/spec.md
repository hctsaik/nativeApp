# Annotation Format Support Specification

## ADDED Requirements

### Requirement: Supported annotation formats are explicit

The annotation service SHALL expose the annotation formats it can import or
export.

#### Scenario: Caller requests supported formats

- WHEN a caller asks for supported annotation formats
- THEN the service SHALL return stable format identifiers
- AND each entry SHALL state whether import and export are supported

### Requirement: ISAT JSON import and export

The annotation service SHALL support native ISAT JSON files.

#### Scenario: ISAT export is requested

- WHEN a canonical annotation set with bbox or polygon geometry is exported as
  ISAT
- THEN the service SHALL write ISAT JSON with `info` and `objects`
- AND SHALL include category, group, segmentation, area, bbox, iscrowd, layer,
  and note values for supported annotations

#### Scenario: ISAT import is requested

- WHEN an ISAT JSON file with `info` and `objects` is imported
- THEN the service SHALL create a canonical annotation set with polygon geometry
- AND SHALL map `category` values to schema labels

### Requirement: YOLO segmentation export

The annotation service SHALL export polygon annotations to YOLO segmentation.

#### Scenario: Polygon annotations are exported

- WHEN YOLO segmentation export is requested
- THEN the service SHALL write normalized class and polygon coordinate rows
- AND SHALL write deterministic class mapping artifacts

#### Scenario: BBox-only annotation is encountered

- WHEN YOLO segmentation export encounters bbox geometry
- THEN it SHALL skip the annotation
- AND SHALL record the unsupported annotation in the conversion report

### Requirement: Mainstream training format import

The annotation service SHALL import supported COCO and YOLO files into canonical
annotation sets.

#### Scenario: COCO file is imported

- WHEN a COCO file contains bbox or polygon segmentation annotations
- THEN the service SHALL map matched images and categories into canonical
  annotations
- AND SHALL report unmatched images or unsupported RLE segmentations

#### Scenario: YOLO detection labels are imported

- WHEN a YOLO detection labels directory is imported
- THEN normalized xywh rows SHALL become pixel-space bbox annotations
- AND label files SHALL match assets by asset id or image stem

#### Scenario: YOLO segmentation labels are imported

- WHEN a YOLO segmentation labels directory is imported
- THEN normalized polygon rows SHALL become pixel-space polygon annotations
- AND label files SHALL match assets by asset id or image stem

### Requirement: Tool-specific project preparation

The annotation service SHALL prepare project folders for supported labeling
tools without making external tool files canonical.

#### Scenario: X-AnyLabeling-compatible project is prepared

- WHEN the selected tool is X-AnyLabeling
- THEN the project SHALL contain copied images, a labels directory, classes file,
  and manifest

#### Scenario: ISAT project is prepared

- WHEN the selected tool is ISAT
- THEN the project SHALL contain copied images, annotation output directory,
  category file, and manifest
