from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from plugins.labeling.domain.core.models import ArtifactRef


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class LocalArtifactStore:
    def __init__(self, workspace_root: Path | str) -> None:
        self.workspace_root = Path(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def put_file(
        self,
        source_path: Path | str,
        relative_dir: str,
        media_type: str,
        artifact_id: str | None = None,
        copy: bool = True,
    ) -> ArtifactRef:
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(source)
        target_dir = self.workspace_root / relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        if copy:
            shutil.copy2(source, target)
        else:
            target = source
        checksum = sha256_file(target)
        return ArtifactRef(
            artifact_id=artifact_id or target.stem,
            uri=target.resolve().as_uri(),
            media_type=media_type,
            sha256=checksum,
            size_bytes=target.stat().st_size,
        )

    def write_bytes(
        self,
        relative_path: str,
        data: bytes,
        media_type: str,
        artifact_id: str | None = None,
    ) -> ArtifactRef:
        target = self.workspace_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        checksum = sha256_file(target)
        return ArtifactRef(
            artifact_id=artifact_id or target.stem,
            uri=target.resolve().as_uri(),
            media_type=media_type,
            sha256=checksum,
            size_bytes=target.stat().st_size,
        )
