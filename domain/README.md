# Annotation Common Component

This package is the Python sidecar MVP for the platform annotation common component.

For the current implementation status, Electron workflow, X-AnyLabeling runtime
installation notes, validation gates, and next steps, see:

```text
docs/ANNOTATION_XANYLABELING.md
```

## Current Scope

- Canonical `annotation-core` dataclasses.
- BBox, polygon, and image-level classification annotations.
- Label schema and attribute schema validation.
- Basic annotation set review state transitions.
- Local workspace storage with SQLite metadata catalog.
- Local artifact writing with checksums.
- LabelMe / X-AnyLabeling-compatible import/export.
- Native ISAT JSON import/export.
- X-AnyLabeling and ISAT project folder preparation without GUI automation.
- Labeling tool runtime detection and optional GUI launch handoff.
- COCO import/export.
- YOLO detection import/export.
- YOLO segmentation import/export.
- Conversion reports for import/export operations.
- Application services for dataset/schema/annotation/review/export workflows.
- Annotation MCP handler support through the repo-level `mcp/annotation_mcp`
  package.

## Package Layout

```text
annotation/
  core/
    models.py
    states.py
    validation.py
  storage/
    artifacts.py
    sqlite_store.py
    workspace.py
  adapters/
    labelme.py
    xanylabeling.py
    xanylabeling_runtime.py
    labeling_runtime.py
    isat.py
    coco.py
    yolo_detection.py
    yolo_segmentation.py
  services.py
  domains/
    animal/
      schema_presets.py
```

## Boundaries

`annotation-core` is the canonical source of truth. LabelMe, X-AnyLabeling, ISAT, COCO, and YOLO files are adapter inputs or derived artifacts.

The MVP intentionally does not include GUI automation, multi-user collaboration, masks, keypoints, tracking, or OCR layout. Those should be added around the same core model and application services rather than changing adapter artifacts into canonical state.

## Service Entry Point

Use `AnnotationService` with `AnnotationWorkspace` for non-MCP callers:

```python
from annotation.services import AnnotationService
from annotation.storage.workspace import AnnotationWorkspace

service = AnnotationService(AnnotationWorkspace("tmp/annotation-workspace"))
dataset = service.create_dataset("animals", "file:///data/animals")
```

## MCP Entry Point

The MCP server lives in `mcp/annotation_mcp` and exposes common
`annotation_*` tools. It uses `ANNOTATION_WORKSPACE` to choose the local
workspace root.

Important multi-format tools:

- `annotation_supported_annotation_formats`
- `annotation_prepare_labeling_project`
- `annotation_detect_labeling_tool`
- `annotation_launch_labeling_project`
- `annotation_import_annotations`
- `annotation_import_project_labels`
- `annotation_create_export`

Supported format identifiers include `labelme`, `x-anylabeling`, `isat`,
`coco`, `yolo-detection`, and `yolo-segmentation`. Aliases such as `yolo-seg`
and `yolo-detect` are normalized by the service.

## X-AnyLabeling Runtime

The project can detect X-AnyLabeling from:

1. `XANYLABELING_EXE`
2. repo-local `.venv-xanylabeling/Scripts/xanylabeling.exe`
3. `PATH`

The GUI launch handoff opens the generated project `images/` folder with:

```text
xanylabeling --filename <project>/images --output <project>/labels --labels <project>/classes.txt --autosave --nodata
```

## ISAT Runtime

ISAT is detected from:

1. `ISAT_EXE`
2. `PATH` command `isat-sam`

The current ISAT-SAM console entry point opens the GUI without documented
project CLI arguments. The platform therefore prepares an ISAT project folder
with `images/`, `annotations/`, `categories.txt`, and `manifest.json`, then
launches the GUI with the project folder as the working directory.
