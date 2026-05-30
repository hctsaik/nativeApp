from __future__ import annotations

from plugins.labeling.domain.core.models import AttributeDef, LabelDef, LabelSchema


def animal_detection_schema(
    labels: list[str] | None = None,
    schema_id: str = "animal_detection_v1",
) -> LabelSchema:
    names = labels or ["cat", "dog", "bird"]
    return LabelSchema(
        id=schema_id,
        name="animal_detection",
        version="1.0",
        task_types=["detection", "classification"],
        labels=[
            LabelDef(
                id=name,
                name=name,
                allowed_geometry_types=["bbox", "polygon", "classification"],
                required_attributes=[],
            )
            for name in names
        ],
        attribute_schema=[
            AttributeDef(
                name="quality",
                value_type="enum",
                required=False,
                enum_values=["good", "uncertain", "bad"],
            )
        ],
    )
