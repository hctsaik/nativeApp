from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# New industrial annotation platform models (Phase 0–3)
# ---------------------------------------------------------------------------

@dataclass
class SystemTenant:
    """已向平台註冊的外部標注系統（對應 system_tenants 表）。"""
    tenant_id: str
    system_name: str
    server_host_name: str
    target_format: str
    api_token: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    # 宣告式連接器選型（rest/file/fake/…）；None 時由 server_host_name 的 scheme 推斷
    connector_type: str | None = None
    # 宣告式連接器設定（如 REST 變體的 endpoint/欄位映射）；接新 REST 系統免寫 class
    connector_config: dict | None = None


@dataclass
class TenantUserMapping:
    """員工與外部系統任務的授權對應（對應 tenant_user_mappings 表）。
    ant_id=None 表示系統層級授權（所有任務）；非 None 表示僅限特定任務。"""
    id: str
    tenant_id: str
    user_id: str
    ant_id: str | None = None


@dataclass
class AnnotationTask:
    """標注任務（對應 annotation_tasks 表）。ant_active: 0=Pending 1=Processing 2=Completed"""
    task_id: str
    tenant_id: str
    ant_id: str
    ant_active: int = 0
    original_classification: str | None = None
    new_classification: str | None = None
    annotation_json: dict = field(default_factory=dict)
    original_annotation_json: dict = field(default_factory=dict)
    external_context: dict = field(default_factory=dict)
    annotated_by: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    delivery_status: dict | None = None


# ---------------------------------------------------------------------------
# Legacy geometry / annotation models — kept for FormatRegistry compatibility
# ---------------------------------------------------------------------------

DatasetState = Literal["created", "ready", "active", "archived"]
AnnotationSetState = Literal[
    "draft", "submitted", "approved", "changes_requested", "rejected", "deprecated"
]
AnnotationSource = Literal["human", "model", "imported", "rule", "fused"]
GeometryType = Literal["bbox", "polygon", "classification"]
CoordinateSpace = Literal["pixel", "normalized"]


@dataclass(slots=True)
class Dataset:
    name: str
    root_uri: str
    id: str = field(default_factory=lambda: new_id("ds"))
    state: DatasetState = "created"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Dataset":
        return cls(**data)


@dataclass(slots=True)
class ImageAsset:
    dataset_id: str
    uri: str
    width: int
    height: int
    checksum: str
    id: str = field(default_factory=lambda: new_id("asset"))
    media_type: str = "image"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ImageAsset":
        return cls(**data)


@dataclass(slots=True)
class AttributeDef:
    name: str
    value_type: Literal["string", "number", "integer", "boolean", "enum"] = "string"
    required: bool = False
    enum_values: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AttributeDef":
        return cls(**data)


@dataclass(slots=True)
class LabelDef:
    id: str
    name: str
    allowed_geometry_types: list[GeometryType]
    color: str | None = None
    required_attributes: list[str] = field(default_factory=list)
    domain_attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LabelDef":
        return cls(**data)


@dataclass(slots=True)
class LabelSchema:
    name: str
    labels: list[LabelDef]
    id: str = field(default_factory=lambda: new_id("schema"))
    version: str = "1.0"
    task_types: list[str] = field(default_factory=lambda: ["detection", "classification"])
    attribute_schema: list[AttributeDef] = field(default_factory=list)
    geometry_constraints: dict[str, Any] = field(default_factory=dict)

    def label_by_id(self, label_id: str) -> LabelDef | None:
        return next((label for label in self.labels if label.id == label_id), None)

    def attribute_by_name(self, name: str) -> AttributeDef | None:
        return next((attr for attr in self.attribute_schema if attr.name == name), None)

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LabelSchema":
        labels = [LabelDef.from_dict(item) for item in data.get("labels", [])]
        attrs = [AttributeDef.from_dict(item) for item in data.get("attribute_schema", [])]
        payload = dict(data)
        payload["labels"] = labels
        payload["attribute_schema"] = attrs
        return cls(**payload)


@dataclass(slots=True)
class BBoxGeometry:
    x: float
    y: float
    width: float
    height: float
    type: Literal["bbox"] = "bbox"
    coordinate_space: CoordinateSpace = "pixel"

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BBoxGeometry":
        payload = dict(data)
        payload.pop("type", None)
        return cls(**payload)


@dataclass(slots=True)
class PolygonGeometry:
    rings: list[list[list[float]]]
    closed: bool = True
    type: Literal["polygon"] = "polygon"
    coordinate_space: CoordinateSpace = "pixel"

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PolygonGeometry":
        payload = dict(data)
        payload.pop("type", None)
        return cls(**payload)


@dataclass(slots=True)
class ClassificationValue:
    label_id: str
    confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClassificationValue":
        return cls(**data)


Geometry = BBoxGeometry | PolygonGeometry


@dataclass(slots=True)
class Annotation:
    asset_id: str
    label_id: str | None = None
    geometry: Geometry | None = None
    classification: list[ClassificationValue] | None = None
    id: str = field(default_factory=lambda: new_id("ann"))
    confidence: float | None = None
    source: AnnotationSource = "human"
    attributes: dict[str, Any] = field(default_factory=dict)
    review_status: str = "draft"
    provenance: dict[str, Any] = field(default_factory=dict)
    version: int = 1

    def geometry_type(self) -> GeometryType:
        if self.geometry is not None:
            return self.geometry.type
        return "classification"

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Annotation":
        payload = dict(data)
        geometry = payload.get("geometry")
        if isinstance(geometry, dict):
            geometry_type = geometry.get("type")
            if geometry_type == "bbox":
                payload["geometry"] = BBoxGeometry.from_dict(geometry)
            elif geometry_type == "polygon":
                payload["geometry"] = PolygonGeometry.from_dict(geometry)
        classification = payload.get("classification")
        if isinstance(classification, list):
            payload["classification"] = [
                ClassificationValue.from_dict(item) for item in classification
            ]
        return cls(**payload)


@dataclass(slots=True)
class AnnotationSet:
    dataset_id: str
    schema_id: str
    annotations: list[Annotation] = field(default_factory=list)
    id: str = field(default_factory=lambda: new_id("aset"))
    source: AnnotationSource = "human"
    state: AnnotationSetState = "draft"
    version: int = 1
    created_by: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnnotationSet":
        payload = dict(data)
        payload["annotations"] = [
            Annotation.from_dict(item) for item in payload.get("annotations", [])
        ]
        return cls(**payload)


@dataclass(slots=True)
class ReviewDecision:
    target_type: Literal["annotation_set", "task", "export"]
    target_id: str
    target_version: int
    decision: Literal["approved", "rejected", "changes_requested"]
    actor_id: str
    comment: str = ""
    id: str = field(default_factory=lambda: new_id("review"))
    decided_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)


@dataclass(slots=True)
class ArtifactRef:
    uri: str
    media_type: str
    sha256: str
    size_bytes: int
    artifact_id: str = field(default_factory=lambda: new_id("artifact"))
    storage_backend: str = "local"
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)


@dataclass(slots=True)
class LossEntry:
    loss_type: str          # "dropped" | "approximated" | "unsupported" | "truncated"
    field: str              # e.g. "geometry", "segmentation", "rle"
    reason: str
    severity: str = "warning"   # "warning" | "error"
    asset_id: str | None = None
    annotation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)


@dataclass(slots=True)
class ConversionReport:
    lossless: bool = True
    dropped_fields: list[str] = field(default_factory=list)
    approximated_fields: list[str] = field(default_factory=list)
    unsupported_annotations: list[str] = field(default_factory=list)
    coordinate_transform: str | None = None
    class_mapping: dict[str, int | str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    source_format_version: str | None = None
    target_format_version: str | None = None
    # Phase 2 additions (backwards compatible — all have defaults)
    losses: list[LossEntry] = field(default_factory=list)
    mapping_version: str | None = None
    summary: str = ""

    def mark_loss(self, field: str, warning: str | None = None) -> None:
        self.lossless = False
        if field not in self.dropped_fields:
            self.dropped_fields.append(field)
        if warning:
            self.warnings.append(warning)

    def add_loss(
        self,
        loss_type: str,
        field: str,
        reason: str,
        severity: str = "warning",
        asset_id: str | None = None,
        annotation_id: str | None = None,
    ) -> None:
        """Add a structured LossEntry and update legacy fields."""
        self.losses.append(LossEntry(loss_type, field, reason, severity, asset_id, annotation_id))
        if severity == "error":
            self.lossless = False
        elif loss_type in {"dropped", "approximated", "unsupported"}:
            self.lossless = False
        if loss_type == "dropped" and field not in self.dropped_fields:
            self.dropped_fields.append(field)
        elif loss_type == "approximated" and field not in self.approximated_fields:
            self.approximated_fields.append(field)
        elif loss_type == "unsupported" and field not in self.unsupported_annotations:
            self.unsupported_annotations.append(field)
        if reason and reason not in self.warnings:
            self.warnings.append(reason)

    def build_summary(self) -> str:
        if self.lossless and not self.losses:
            return "lossless"
        errors = [e for e in self.losses if e.severity == "error"]
        warnings = [e for e in self.losses if e.severity == "warning"]
        if errors:
            return f"{len(errors)} error(s), {len(warnings)} warning(s)"
        if warnings:
            return f"{len(warnings)} warning(s)"
        return "lossless"

    def to_dict(self) -> dict[str, Any]:
        d = _to_dict(self)
        d["summary"] = self.build_summary()
        return d


@dataclass(slots=True)
class AdapterResult:
    artifact_refs: list[ArtifactRef] = field(default_factory=list)
    conversion_report: ConversionReport = field(default_factory=ConversionReport)
    job_id: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)


def _to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {name: _to_dict(getattr(value, name)) for name in value.__dataclass_fields__}
    if isinstance(value, list):
        return [_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_dict(item) for key, item in value.items()}
    return value
