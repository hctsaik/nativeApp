# Annotation Core Specification

## ADDED Requirements

### Requirement: Canonical annotation truth

The platform SHALL treat `annotation-core` annotation sets as the only canonical source of truth for annotation data.

#### Scenario: External format is imported

- WHEN LabelMe, X-AnyLabeling, COCO, or YOLO data is imported
- THEN the system SHALL convert the data into a canonical annotation set
- AND SHALL NOT treat the external file as canonical truth

#### Scenario: External format is exported

- WHEN annotation data is exported to LabelMe, X-AnyLabeling, COCO, or YOLO
- THEN the system SHALL create a derived export artifact
- AND the export artifact SHALL reference the source annotation set

### Requirement: MVP image annotation model

The annotation core SHALL support image assets with bbox, polygon, and image-level classification annotations for the MVP.

#### Scenario: BBox annotation is saved

- WHEN a user saves a bbox annotation
- THEN the annotation SHALL include an asset ID, label ID, geometry type, pixel or normalized coordinates, source, version, and schema reference

#### Scenario: Polygon annotation is saved

- WHEN a user saves a polygon annotation
- THEN the annotation SHALL include at least one closed ring with at least three points
- AND the annotation SHALL reference the label schema that allows polygon geometry

#### Scenario: Image classification is saved

- WHEN a user saves an image-level classification
- THEN the annotation SHALL reference the image asset
- AND SHALL store the classification value without requiring shape geometry

### Requirement: Schema-governed labels and attributes

The annotation core SHALL validate labels and domain attributes against `LabelSchema` and `AttributeSchema` definitions.

#### Scenario: Unknown label is used

- WHEN an annotation references a label ID that is not present in the schema
- THEN validation SHALL return an error issue

#### Scenario: Required attribute is missing

- WHEN an annotation omits a required attribute defined by the schema
- THEN validation SHALL return an error issue with a field path

### Requirement: Local MVP storage with replaceable ports

The MVP SHALL use a local workspace folder and SQLite catalog while keeping metadata and artifact access behind storage ports.

#### Scenario: Image asset is ingested

- WHEN an image asset is ingested
- THEN the metadata SHALL be recorded in the metadata store
- AND the original file or managed copy SHALL be represented by an artifact reference

#### Scenario: Storage backend changes later

- WHEN a future implementation replaces SQLite or local file storage
- THEN application services SHALL continue to use the metadata and artifact store interfaces

### Requirement: Review and approval workflow

The annotation core SHALL support basic review and approval for annotation sets.

#### Scenario: Annotation set is approved

- WHEN a submitted annotation set passes review
- THEN the system SHALL record an immutable approval decision
- AND SHALL transition the annotation set to approved

#### Scenario: Changes are requested

- WHEN a reviewer requests changes
- THEN the system SHALL record the review decision
- AND SHALL return the annotation set to draft through a changes-requested state

### Requirement: Export state rules

The annotation core SHALL distinguish preview exports from training or publish exports.

#### Scenario: Draft set is exported

- WHEN a draft annotation set is exported
- THEN the export SHALL be marked as preview

#### Scenario: Training export is requested

- WHEN a training or publish export is requested
- THEN the source annotation set SHALL be approved

### Requirement: Structured validation issues

The annotation core SHALL return validation issues with stable structured fields.

#### Scenario: Validation fails

- WHEN validation finds an invalid annotation
- THEN each issue SHALL include severity, code, message, optional annotation ID, optional asset ID, field path, and rule ID

### Requirement: Generic annotation MCP surface

The platform SHALL expose annotation data and workflow operations through generic `annotation_*` MCP tools and `annotation://` resources.

#### Scenario: Agent lists annotation resources

- WHEN an MCP client requests annotation resources
- THEN the system SHALL expose resources under the `annotation://` URI namespace
- AND SHALL NOT require animal-specific resource names for core operations

#### Scenario: Agent calls annotation tool

- WHEN an MCP client creates a dataset, schema, task, annotation set, validation report, review decision, or export
- THEN the tool name SHALL use the `annotation_*` prefix for common operations
