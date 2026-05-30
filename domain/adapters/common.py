from __future__ import annotations

import json
from pathlib import Path

from plugins.labeling.domain.core.models import ArtifactRef, ConversionReport
from plugins.labeling.domain.storage.artifacts import sha256_file


def write_json_artifact(path: Path, payload: dict, media_type: str = "application/json") -> ArtifactRef:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return ArtifactRef(
        artifact_id=path.stem,
        uri=path.resolve().as_uri(),
        media_type=media_type,
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
    )


def write_conversion_report(path: Path, report: ConversionReport) -> ArtifactRef:
    return write_json_artifact(path, report.to_dict())
