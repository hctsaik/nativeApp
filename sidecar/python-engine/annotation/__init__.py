"""Reusable annotation common component for the Python sidecar."""

from annotation.core.models import (
    Annotation,
    AnnotationSet,
    AttributeDef,
    BBoxGeometry,
    ClassificationValue,
    Dataset,
    ImageAsset,
    LabelDef,
    LabelSchema,
    PolygonGeometry,
)
from annotation.core.validation import ValidationIssue, validate_annotation_set

__all__ = [
    "Annotation",
    "AnnotationSet",
    "AttributeDef",
    "BBoxGeometry",
    "ClassificationValue",
    "Dataset",
    "ImageAsset",
    "LabelDef",
    "LabelSchema",
    "PolygonGeometry",
    "ValidationIssue",
    "validate_annotation_set",
]
