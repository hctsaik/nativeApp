from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from plugins.labeling.domain.formats.contracts import FormatCapabilities, FormatDescriptor

if TYPE_CHECKING:
    from plugins.labeling.domain.core.models import AdapterResult, AnnotationSet, ConversionReport, ImageAsset, LabelSchema
    from plugins.labeling.domain.formats.registry import FormatRegistry


# ── Adapter wrappers ────────────────────────────────────────────────────────


class _LabelMeAdapter:
    """Wraps labelme / x-anylabeling adapters (same file format)."""

    def export(self, annotation_set, schema, assets, output_dir, *, dry_run=False):
        from plugins.labeling.domain.adapters.labelme import export_labelme
        if dry_run:
            with tempfile.TemporaryDirectory() as tmp:
                return export_labelme(annotation_set, schema, assets, Path(tmp))
        return export_labelme(annotation_set, schema, assets, output_dir)

    def import_file(self, path, dataset_id, schema, asset, all_assets):
        from plugins.labeling.domain.adapters.labelme import import_labelme_file
        return import_labelme_file(path, dataset_id, schema, asset)

    def import_dir(self, path, dataset_id, schema, assets):
        from plugins.labeling.domain.adapters.labelme import import_labelme_project_dir
        return import_labelme_project_dir(path, dataset_id, schema, assets)


class _IsatAdapter:
    def export(self, annotation_set, schema, assets, output_dir, *, dry_run=False):
        from plugins.labeling.domain.adapters.isat import export_isat
        if dry_run:
            with tempfile.TemporaryDirectory() as tmp:
                return export_isat(annotation_set, schema, assets, Path(tmp))
        return export_isat(annotation_set, schema, assets, output_dir)

    def import_file(self, path, dataset_id, schema, asset, all_assets):
        from plugins.labeling.domain.adapters.isat import import_isat_file
        return import_isat_file(path, dataset_id, schema, asset)

    def import_dir(self, path, dataset_id, schema, assets):
        from plugins.labeling.domain.adapters.isat import import_isat_project_dir
        return import_isat_project_dir(path, dataset_id, schema, assets)


class _CocoAdapter:
    def export(self, annotation_set, schema, assets, output_dir, *, dry_run=False):
        from plugins.labeling.domain.adapters.coco import export_coco
        if dry_run:
            with tempfile.TemporaryDirectory() as tmp:
                return export_coco(annotation_set, schema, assets, Path(tmp))
        return export_coco(annotation_set, schema, assets, output_dir)

    def import_file(self, path, dataset_id, schema, asset, all_assets):
        from plugins.labeling.domain.adapters.coco import import_coco_file
        ann_set, report, _unmatched = import_coco_file(path, dataset_id, schema, all_assets)
        return ann_set, report

    def import_dir(self, path, dataset_id, schema, assets):
        raise NotImplementedError("COCO does not support project-level directory import")


class _YoloDetectionAdapter:
    def export(self, annotation_set, schema, assets, output_dir, *, dry_run=False):
        from plugins.labeling.domain.adapters.yolo_detection import export_yolo_detection
        if dry_run:
            with tempfile.TemporaryDirectory() as tmp:
                return export_yolo_detection(annotation_set, schema, assets, Path(tmp))
        return export_yolo_detection(annotation_set, schema, assets, output_dir)

    def import_file(self, path, dataset_id, schema, asset, all_assets):
        raise NotImplementedError("YOLO detection import requires a directory")

    def import_dir(self, path, dataset_id, schema, assets):
        from plugins.labeling.domain.adapters.yolo_detection import import_yolo_detection_dir
        return import_yolo_detection_dir(path, dataset_id, schema, assets)


class _YoloSegmentationAdapter:
    def export(self, annotation_set, schema, assets, output_dir, *, dry_run=False):
        from plugins.labeling.domain.adapters.yolo_segmentation import export_yolo_segmentation
        if dry_run:
            with tempfile.TemporaryDirectory() as tmp:
                return export_yolo_segmentation(annotation_set, schema, assets, Path(tmp))
        return export_yolo_segmentation(annotation_set, schema, assets, output_dir)

    def import_file(self, path, dataset_id, schema, asset, all_assets):
        raise NotImplementedError("YOLO segmentation import requires a directory")

    def import_dir(self, path, dataset_id, schema, assets):
        from plugins.labeling.domain.adapters.yolo_segmentation import import_yolo_segmentation_dir
        return import_yolo_segmentation_dir(path, dataset_id, schema, assets)


# ── Registration ─────────────────────────────────────────────────────────────


def register_builtins(registry: FormatRegistry) -> None:
    _lm_caps = FormatCapabilities(
        can_import=True, can_export=True, requires_asset=True,
        supports_polygon=True, supports_bbox=True, supports_classification=True,
        lossless_roundtrip=True, supports_import_dir=True,
    )
    registry.register(
        FormatDescriptor("labelme", "LabelMe JSON", _lm_caps, aliases=["label-me"]),
        _LabelMeAdapter(),
    )
    registry.register(
        FormatDescriptor(
            "x-anylabeling", "X-AnyLabeling JSON", _lm_caps,
            aliases=["xanylabeling", "x-any", "x_anylabeling"],
        ),
        _LabelMeAdapter(),
    )
    registry.register(
        FormatDescriptor(
            "isat", "ISAT JSON",
            FormatCapabilities(
                can_import=True, can_export=True, requires_asset=True,
                supports_polygon=True, supports_bbox=True, supports_classification=False,
                lossless_roundtrip=False, supports_import_dir=True,
            ),
        ),
        _IsatAdapter(),
    )
    registry.register(
        FormatDescriptor(
            "coco", "COCO JSON",
            FormatCapabilities(
                can_import=True, can_export=True, requires_asset=False,
                supports_polygon=True, supports_bbox=True, supports_classification=False,
                lossless_roundtrip=False, supports_import_dir=False,
            ),
            aliases=["coco-json"],
        ),
        _CocoAdapter(),
    )
    registry.register(
        FormatDescriptor(
            "yolo-detection", "YOLO Detection",
            FormatCapabilities(
                can_import=True, can_export=True, requires_asset=True,
                supports_polygon=False, supports_bbox=True, supports_classification=False,
                lossless_roundtrip=False, supports_import_dir=True,
            ),
            aliases=["yolo", "yolo-detect", "yolo_detection"],
        ),
        _YoloDetectionAdapter(),
    )
    registry.register(
        FormatDescriptor(
            "yolo-segmentation", "YOLO Segmentation",
            FormatCapabilities(
                can_import=True, can_export=True, requires_asset=True,
                supports_polygon=True, supports_bbox=False, supports_classification=False,
                lossless_roundtrip=False, supports_import_dir=True,
            ),
            aliases=["yolo-seg", "yolo-segment", "yolo_segmentation", "yolo-segmentations"],
        ),
        _YoloSegmentationAdapter(),
    )
