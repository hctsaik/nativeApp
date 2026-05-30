from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from plugins.labeling.domain.core.models import AdapterResult, AnnotationSet, ConversionReport, ImageAsset, LabelSchema


@dataclass
class FormatCapabilities:
    can_import: bool = True
    can_export: bool = True
    # False for COCO (full-file import, no per-asset pairing needed)
    requires_asset: bool = True
    supports_polygon: bool = True
    supports_bbox: bool = True
    supports_classification: bool = True
    lossless_roundtrip: bool = False
    # False for formats that have no directory-level import (e.g., COCO)
    supports_import_dir: bool = True


@dataclass
class FormatDescriptor:
    format_id: str
    display_name: str
    capabilities: FormatCapabilities
    aliases: list[str] = field(default_factory=list)


@runtime_checkable
class FormatAdapter(Protocol):
    def export(
        self,
        annotation_set: AnnotationSet,
        schema: LabelSchema,
        assets: dict[str, ImageAsset],
        output_dir: Path,
        *,
        dry_run: bool = False,
    ) -> AdapterResult: ...

    def import_file(
        self,
        path: str,
        dataset_id: str,
        schema: LabelSchema,
        asset: ImageAsset | None,
        all_assets: list[ImageAsset],
    ) -> tuple[AnnotationSet, ConversionReport]: ...

    def import_dir(
        self,
        path: Path,
        dataset_id: str,
        schema: LabelSchema,
        assets: list[ImageAsset],
    ) -> tuple[AnnotationSet, ConversionReport, list[str]]: ...
