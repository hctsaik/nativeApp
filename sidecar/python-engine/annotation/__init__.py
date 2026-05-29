"""Back-compat shim for the `annotation` import name (platform restructure P6).

The annotation package now physically lives at
``sidecar/python-engine/plugins/labeling/domain/`` (Labeling plugin home, owner
decision D1/D2). This stub keeps the ``annotation`` import name working by
redirecting the package search path there, so every existing absolute
``from annotation...`` import (engine sidecar, scripts/module_*, mcp, tests)
keeps resolving unchanged and to a single module identity.

Canonical source: plugins/labeling/domain/  (see plugins/labeling/plugin.manifest.yaml)
Remove this shim only once all import sites move off the `annotation` name and a
full /package-build + golden-path run validates the bundle.
"""

import os as _os

# Redirect submodule lookup (annotation.core, annotation.services, ...) to the
# relocated package directory. annotation uses 100% absolute self-imports, so a
# single __path__ redirect preserves one consistent module identity.
__path__ = [_os.path.join(_os.path.dirname(__file__), "..", "plugins", "labeling", "domain")]

# Re-export the public API (mirrors the original annotation/__init__.py surface).
from annotation.core.models import (  # noqa: E402
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
from annotation.core.validation import ValidationIssue, validate_annotation_set  # noqa: E402

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
