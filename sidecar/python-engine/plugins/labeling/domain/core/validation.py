from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from plugins.labeling.domain.core.models import (
    Annotation,
    AnnotationSet,
    BBoxGeometry,
    ImageAsset,
    LabelSchema,
    PolygonGeometry,
)


@dataclass(slots=True)
class ValidationIssue:
    severity: str
    code: str
    message: str
    annotation_id: str | None = None
    asset_id: str | None = None
    field_path: str | None = None
    rule_id: str | None = None
    suggested_fix: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "annotation_id": self.annotation_id,
            "asset_id": self.asset_id,
            "field_path": self.field_path,
            "rule_id": self.rule_id,
            "suggested_fix": self.suggested_fix,
        }


def validate_annotation_set(
    annotation_set: AnnotationSet,
    schema: LabelSchema,
    assets: dict[str, ImageAsset],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if annotation_set.schema_id != schema.id:
        issues.append(
            ValidationIssue(
                severity="error",
                code="SCHEMA_MISMATCH",
                message="Annotation set schema_id does not match the provided schema.",
                field_path="schema_id",
                rule_id="core.schema_match",
            )
        )
    for index, annotation in enumerate(annotation_set.annotations):
        issues.extend(_validate_annotation(annotation, schema, assets, index))
    return issues


def _validate_annotation(
    annotation: Annotation,
    schema: LabelSchema,
    assets: dict[str, ImageAsset],
    index: int,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    base_path = f"annotations[{index}]"
    asset = assets.get(annotation.asset_id)
    if asset is None:
        issues.append(
            _issue(
                "UNKNOWN_ASSET",
                "Annotation references an unknown asset.",
                annotation,
                f"{base_path}.asset_id",
                "core.asset_exists",
            )
        )

    label = schema.label_by_id(annotation.label_id or "")
    if label is None:
        issues.append(
            _issue(
                "UNKNOWN_LABEL",
                "Annotation references a label that is not in the schema.",
                annotation,
                f"{base_path}.label_id",
                "core.label_exists",
            )
        )
    else:
        geometry_type = annotation.geometry_type()
        if geometry_type not in label.allowed_geometry_types:
            issues.append(
                _issue(
                    "GEOMETRY_NOT_ALLOWED",
                    f"Label does not allow {geometry_type} geometry.",
                    annotation,
                    f"{base_path}.geometry.type",
                    "core.allowed_geometry",
                )
            )
        issues.extend(_validate_required_attributes(annotation, schema, label.required_attributes, base_path))

    if isinstance(annotation.geometry, BBoxGeometry):
        issues.extend(_validate_bbox(annotation, annotation.geometry, asset, base_path))
    elif isinstance(annotation.geometry, PolygonGeometry):
        issues.extend(_validate_polygon(annotation, annotation.geometry, asset, base_path))
    elif annotation.geometry is None and not annotation.classification:
        issues.append(
            _issue(
                "EMPTY_ANNOTATION",
                "Annotation has neither geometry nor classification.",
                annotation,
                f"{base_path}.geometry",
                "core.non_empty_annotation",
            )
        )
    return issues


def _validate_required_attributes(
    annotation: Annotation,
    schema: LabelSchema,
    required_names: list[str],
    base_path: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    required = set(required_names)
    for name in sorted(required):
        if name not in annotation.attributes or annotation.attributes[name] in (None, ""):
            issues.append(
                _issue(
                    "REQUIRED_ATTRIBUTE_MISSING",
                    f"Required attribute '{name}' is missing.",
                    annotation,
                    f"{base_path}.attributes.{name}",
                    "core.required_attribute",
                )
            )
            continue
        attr_def = schema.attribute_by_name(name)
        if attr_def is not None and not _attribute_value_matches(annotation.attributes[name], attr_def):
            issues.append(
                _issue(
                    "ATTRIBUTE_TYPE_INVALID",
                    f"Attribute '{name}' does not match its schema type.",
                    annotation,
                    f"{base_path}.attributes.{name}",
                    "core.attribute_type",
                )
            )
    return issues


def _attribute_value_matches(value: Any, attr_def: Any) -> bool:
    if attr_def.value_type == "string":
        return isinstance(value, str)
    if attr_def.value_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if attr_def.value_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if attr_def.value_type == "boolean":
        return isinstance(value, bool)
    if attr_def.value_type == "enum":
        return isinstance(value, str) and value in attr_def.enum_values
    return True


def _validate_bbox(
    annotation: Annotation,
    bbox: BBoxGeometry,
    asset: ImageAsset | None,
    base_path: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    values = [bbox.x, bbox.y, bbox.width, bbox.height]
    if not all(isinstance(value, (int, float)) and isfinite(value) for value in values):
        issues.append(_issue("INVALID_COORDINATE", "BBox coordinates must be finite.", annotation, f"{base_path}.geometry", "core.finite_coordinates"))
        return issues
    if bbox.width <= 0 or bbox.height <= 0:
        issues.append(_issue("INVALID_BBOX_SIZE", "BBox width and height must be positive.", annotation, f"{base_path}.geometry", "core.bbox_positive_size"))
    if asset and bbox.coordinate_space == "pixel":
        if bbox.x < 0 or bbox.y < 0 or bbox.x + bbox.width > asset.width or bbox.y + bbox.height > asset.height:
            issues.append(_issue("GEOMETRY_OUT_OF_BOUNDS", "BBox is outside image bounds.", annotation, f"{base_path}.geometry", "core.geometry_bounds"))
    return issues


def _validate_polygon(
    annotation: Annotation,
    polygon: PolygonGeometry,
    asset: ImageAsset | None,
    base_path: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not polygon.rings:
        return [_issue("INVALID_POLYGON", "Polygon must contain at least one ring.", annotation, f"{base_path}.geometry.rings", "core.polygon_ring")]
    ring = polygon.rings[0]
    if len(ring) < 3:
        issues.append(_issue("INVALID_POLYGON", "Polygon requires at least three points.", annotation, f"{base_path}.geometry.rings[0]", "core.polygon_min_points"))
        return issues
    for point_index, point in enumerate(ring):
        if len(point) != 2 or not all(isinstance(value, (int, float)) and isfinite(value) for value in point):
            issues.append(_issue("INVALID_COORDINATE", "Polygon points must be finite x/y pairs.", annotation, f"{base_path}.geometry.rings[0][{point_index}]", "core.finite_coordinates"))
        elif asset and polygon.coordinate_space == "pixel":
            x, y = point
            if x < 0 or y < 0 or x > asset.width or y > asset.height:
                issues.append(_issue("GEOMETRY_OUT_OF_BOUNDS", "Polygon point is outside image bounds.", annotation, f"{base_path}.geometry.rings[0][{point_index}]", "core.geometry_bounds"))
    if abs(_polygon_area(ring)) <= 0:
        issues.append(_issue("INVALID_POLYGON_AREA", "Polygon area must be greater than zero.", annotation, f"{base_path}.geometry.rings[0]", "core.polygon_area"))
    return issues


def _polygon_area(points: list[list[float]]) -> float:
    area = 0.0
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        area += x1 * y2 - x2 * y1
    return area / 2.0


def _issue(
    code: str,
    message: str,
    annotation: Annotation,
    field_path: str,
    rule_id: str,
) -> ValidationIssue:
    return ValidationIssue(
        severity="error",
        code=code,
        message=message,
        annotation_id=annotation.id,
        asset_id=annotation.asset_id,
        field_path=field_path,
        rule_id=rule_id,
    )
