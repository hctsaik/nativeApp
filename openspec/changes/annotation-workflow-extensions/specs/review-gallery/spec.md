# Review Gallery Specification

## ADDED Requirements

### Requirement: Visual grid of annotated images with bbox overlays

The review gallery SHALL display a paginated grid of images from the current
manifest with bounding box overlays drawn on each thumbnail.

#### Scenario: Annotated image is displayed

- WHEN the gallery renders a thumbnail for an image with annotation shapes
- THEN each rectangle shape SHALL be drawn as a colored outline on the thumbnail
- AND the shape label SHALL be rendered as text near the top-left corner of the box

#### Scenario: Unannotated image is displayed

- WHEN the gallery renders a thumbnail for an image with no annotation shapes
- THEN the thumbnail SHALL be displayed without any overlay
- AND the image SHALL be eligible for filtering by status

### Requirement: Thumbnail overlay is cached by file mtime

#### Scenario: Annotation file has not changed since last render

- WHEN the gallery re-renders after a Streamlit rerun
- THEN the thumbnail SHALL be served from cache without re-reading the image file
  or re-running PIL ImageDraw

#### Scenario: Annotation file has been modified

- WHEN the annotation `.json` mtime has changed since the last render
- THEN the cache SHALL be invalidated and the thumbnail SHALL be re-rendered

### Requirement: Paginated gallery with configurable page size

#### Scenario: Manifest has more images than one page

- WHEN the number of filtered images exceeds PAGE_SIZE
- THEN the gallery SHALL display only the current page
- AND SHALL provide Previous and Next navigation buttons
- AND SHALL display the current page number and total page count

### Requirement: Filter by label, status, and bbox count

#### Scenario: User filters by label

- WHEN one or more labels are selected in the filter panel
- THEN the gallery SHALL show only images that contain at least one shape
  with one of the selected labels

#### Scenario: User filters by annotation status

- WHEN status filter is set to "annotated"
- THEN the gallery SHALL show only images with at least one shape
- WHEN status filter is set to "unannotated"
- THEN the gallery SHALL show only images with no shapes

#### Scenario: User filters by minimum bbox count

- WHEN the minimum bbox count slider is set to N
- THEN the gallery SHALL show only images with at least N shapes

### Requirement: Detail view on thumbnail click

#### Scenario: Annotator clicks a thumbnail

- WHEN a thumbnail is clicked
- THEN the gallery grid SHALL be replaced by a detail view
- AND the detail view SHALL show the full-resolution image with overlays
  scaled to fit the available width
- AND SHALL show a table of all shapes with label, shape type, and bounding box area
- AND SHALL provide a Back button to return to the grid

### Requirement: Open in X-AnyLabeling from detail view

#### Scenario: Annotator clicks Open in X-AnyLabeling

- WHEN the Open button is clicked in the detail view
- THEN the system SHALL launch X-AnyLabeling with the image path as an argument
  via subprocess
- AND SHALL NOT block the Streamlit UI while X-AnyLabeling is open

### Requirement: Flag image for re-annotation

#### Scenario: Annotator flags an image

- WHEN the Flag for re-annotation button is clicked in the detail view
- THEN the system SHALL write a sidecar `.flag` file alongside the image
- AND the thumbnail in the gallery SHALL display a visual indicator

#### Scenario: Flag is cleared

- WHEN the flag sidecar file is deleted
- THEN the visual indicator SHALL disappear on the next gallery render
