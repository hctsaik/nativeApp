# Design

## Separation

The platform separates two concepts:

- **Annotation formats**: file contracts used for import/export, such as
  `labelme`, `x-anylabeling`, `isat`, `coco`, `yolo-detection`, and
  `yolo-segmentation`.
- **Labeling tools**: launchable applications or prepared project workflows,
  such as `labelme`, `x-anylabeling`, and `isat`.

The canonical `annotation-core` model remains the system of record. Tool files
are generated artifacts or imported sources.

## Format Support Matrix

| Format | Import | Export | Notes |
| --- | --- | --- | --- |
| LabelMe | yes | yes | `shapes` JSON, bbox, polygon, image-level classification in flags |
| X-AnyLabeling | yes | yes | LabelMe-compatible JSON with four-point rectangle compatibility |
| ISAT | yes | yes | `info` + `objects`, polygon-first, bbox preserved for bbox annotations |
| COCO | yes | yes | Polygon and bbox import/export; RLE is reported as unsupported |
| YOLO detection | yes | yes | BBox import/export using schema order class IDs |
| YOLO segmentation | yes | yes | Polygon import/export; bbox skipped with report on export |

## Adapter Rules

- Every import/export returns a `ConversionReport`.
- Unsupported geometry is skipped only with a report warning.
- X-AnyLabeling remains LabelMe-compatible at the format layer.
- ISAT stores polygons in `objects[].segmentation`; bbox-only annotations are
  exported as four-corner segmentation polygons and marked approximated.
- YOLO segmentation uses normalized polygon coordinates and deterministic class
  IDs from schema order.
