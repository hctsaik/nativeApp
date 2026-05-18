# X-AnyLabeling Adapter Specification

## ADDED Requirements

### Requirement: Adapter uses annotation core as canonical source

The X-AnyLabeling adapter SHALL exchange data with `annotation-core` without making X-AnyLabeling files canonical truth.

#### Scenario: Project files are generated

- WHEN the adapter prepares an X-AnyLabeling project
- THEN it SHALL read data from canonical datasets, assets, schemas, and annotation sets
- AND SHALL write generated project files as artifacts

#### Scenario: Edited files are imported

- WHEN LabelMe or X-AnyLabeling JSON files are imported
- THEN the adapter SHALL create a new canonical annotation set version or derived annotation set
- AND SHALL NOT silently overwrite an approved annotation set

### Requirement: Project folder preparation

The adapter SHALL prepare a local X-AnyLabeling-compatible project folder without GUI automation.

#### Scenario: Project is prepared

- WHEN a dataset and schema are selected for X-AnyLabeling
- THEN the adapter SHALL create a project folder with image assets, label files or label directory, class configuration, and a manifest

#### Scenario: GUI control is requested

- WHEN a caller needs to open or control the X-AnyLabeling GUI
- THEN that behavior SHALL be handled outside the MVP adapter contract

### Requirement: LabelMe and X-AnyLabeling round trip

The adapter SHALL support round trips for bbox, polygon, and supported image-level classification data.

#### Scenario: BBox round trip is run

- WHEN a canonical bbox annotation set is exported and imported through LabelMe or X-AnyLabeling files
- THEN supported bbox coordinates and label mappings SHALL be preserved within the configured tolerance

#### Scenario: Polygon round trip is run

- WHEN a canonical polygon annotation set is exported and imported through LabelMe or X-AnyLabeling files
- THEN supported polygon coordinates and label mappings SHALL be preserved within the configured tolerance

#### Scenario: Classification is unsupported by target format

- WHEN image-level classification cannot be represented by the selected target format
- THEN the adapter SHALL report the unsupported field in the conversion report

### Requirement: Conversion reports for adapter operations

Every import or export operation SHALL produce a conversion report.

#### Scenario: Lossy export is created

- WHEN an export cannot preserve all canonical fields
- THEN the conversion report SHALL mark the operation as not lossless
- AND SHALL list dropped or approximated fields

#### Scenario: Unsupported geometry is encountered

- WHEN an annotation contains geometry not supported by the MVP adapter
- THEN the adapter SHALL report the annotation as unsupported
- AND SHALL NOT silently drop it without a warning

### Requirement: COCO export

The adapter SHALL export approved canonical annotation sets to COCO artifacts for supported geometry.

#### Scenario: COCO export is requested

- WHEN an approved annotation set with supported annotations is exported to COCO
- THEN the adapter SHALL create COCO files, an export manifest, and a conversion report

### Requirement: YOLO detection export

The adapter SHALL export approved canonical bbox annotation sets to YOLO detection artifacts.

#### Scenario: YOLO detection export is requested

- WHEN an approved annotation set with bbox annotations is exported to YOLO detection
- THEN the adapter SHALL create YOLO label files, deterministic class mapping, an export manifest, and a conversion report

#### Scenario: Non-bbox geometry is exported to YOLO detection

- WHEN a YOLO detection export encounters non-bbox geometry
- THEN the adapter SHALL omit or approximate the geometry according to configured rules
- AND SHALL record the decision in the conversion report
