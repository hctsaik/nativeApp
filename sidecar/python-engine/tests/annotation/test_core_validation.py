from __future__ import annotations

import pytest

from plugins.labeling.domain.core.models import (
    Annotation,
    AnnotationSet,
    AttributeDef,
    BBoxGeometry,
    ClassificationValue,
    ImageAsset,
    LabelDef,
    LabelSchema,
    PolygonGeometry,
)
from plugins.labeling.domain.core.states import InvalidStateTransition, apply_review_decision, transition_annotation_set
from plugins.labeling.domain.core.validation import validate_annotation_set


def _schema() -> LabelSchema:
    return LabelSchema(
        id="schema_animals",
        name="animals",
        labels=[
            LabelDef(
                id="dog",
                name="dog",
                allowed_geometry_types=["bbox", "polygon"],
                required_attributes=["quality"],
            ),
            LabelDef(id="scene_ok", name="scene_ok", allowed_geometry_types=["classification"]),
        ],
        attribute_schema=[AttributeDef(name="quality", value_type="enum", required=True, enum_values=["good", "bad"])],
    )


def _asset() -> ImageAsset:
    return ImageAsset(
        id="asset_1",
        dataset_id="ds_1",
        uri="file:///tmp/dog.jpg",
        width=100,
        height=80,
        checksum="abc",
    )


def test_valid_bbox_annotation_passes() -> None:
    schema = _schema()
    asset = _asset()
    annotation_set = AnnotationSet(
        id="aset_1",
        dataset_id="ds_1",
        schema_id=schema.id,
        annotations=[
            Annotation(
                asset_id=asset.id,
                label_id="dog",
                geometry=BBoxGeometry(x=10, y=15, width=30, height=20),
                attributes={"quality": "good"},
            )
        ],
    )

    assert validate_annotation_set(annotation_set, schema, {asset.id: asset}) == []


def test_invalid_bbox_reports_structured_issues() -> None:
    schema = _schema()
    asset = _asset()
    annotation_set = AnnotationSet(
        dataset_id="ds_1",
        schema_id=schema.id,
        annotations=[
            Annotation(
                asset_id=asset.id,
                label_id="dog",
                geometry=BBoxGeometry(x=90, y=70, width=30, height=20),
            )
        ],
    )

    issues = validate_annotation_set(annotation_set, schema, {asset.id: asset})
    codes = {issue.code for issue in issues}

    assert "GEOMETRY_OUT_OF_BOUNDS" in codes
    assert "REQUIRED_ATTRIBUTE_MISSING" in codes
    assert all(issue.field_path for issue in issues)


def test_polygon_and_image_classification_are_supported() -> None:
    schema = _schema()
    asset = _asset()
    annotation_set = AnnotationSet(
        dataset_id="ds_1",
        schema_id=schema.id,
        annotations=[
            Annotation(
                asset_id=asset.id,
                label_id="dog",
                geometry=PolygonGeometry(rings=[[[1, 1], [20, 1], [20, 20]]]),
                attributes={"quality": "bad"},
            ),
            Annotation(
                asset_id=asset.id,
                label_id="scene_ok",
                classification=[ClassificationValue(label_id="scene_ok")],
            ),
        ],
    )

    assert validate_annotation_set(annotation_set, schema, {asset.id: asset}) == []


def test_review_state_machine_records_decision() -> None:
    annotation_set = AnnotationSet(dataset_id="ds_1", schema_id="schema_1")
    transition_annotation_set(annotation_set, "submitted")

    decision = apply_review_decision(annotation_set, "approved", actor_id="reviewer")

    assert annotation_set.state == "approved"
    assert decision.target_id == annotation_set.id
    assert decision.decision == "approved"


def test_invalid_state_transition_raises() -> None:
    annotation_set = AnnotationSet(dataset_id="ds_1", schema_id="schema_1")

    with pytest.raises(InvalidStateTransition):
        transition_annotation_set(annotation_set, "approved")
