from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from plugins.labeling.domain.formats.registry import reset_format_registry
from plugins.labeling.domain.services import AnnotationService
from plugins.labeling.domain.storage.workspace import AnnotationWorkspace


def _write_image(path: Path) -> None:
    Image.new("RGB", (100, 80), color=(1, 2, 3)).save(path)


def _service(tmp_path: Path) -> AnnotationService:
    reset_format_registry()
    return AnnotationService(AnnotationWorkspace(tmp_path / "workspace"))


def _seed_with_bbox(service: AnnotationService, tmp_path: Path):
    img = tmp_path / "img.png"
    _write_image(img)
    ds = service.create_dataset("test", str(tmp_path))
    asset = service.ingest_assets(ds["id"], [str(img)])["assets"][0]
    schema = service.create_schema(
        "labels",
        [{"id": "cat", "name": "cat", "allowed_geometry_types": ["bbox"]}],
    )
    aset = service.create_annotation_set(
        ds["id"], schema["id"],
        [{"asset_id": asset["id"], "label_id": "cat",
          "geometry": {"type": "bbox", "x": 10, "y": 10, "width": 20, "height": 20}}],
    )
    return aset["id"], schema["id"]


def test_dry_run_does_not_write_files(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    aset_id, _ = _seed_with_bbox(svc, tmp_path)

    before = set(tmp_path.rglob("*.json"))
    report = svc.dry_run_export(aset_id, "labelme")
    after = set(tmp_path.rglob("*.json"))

    # Only the annotation set JSON should exist (written by ingest), no new files
    new_files = after - before
    assert len(new_files) == 0, f"dry_run wrote files: {new_files}"


def test_dry_run_returns_conversion_report_dict(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    aset_id, _ = _seed_with_bbox(svc, tmp_path)
    report = svc.dry_run_export(aset_id, "labelme")
    assert isinstance(report, dict)
    assert "lossless" in report
    assert "losses" in report
    assert "summary" in report


def test_dry_run_lossless_for_labelme(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    aset_id, _ = _seed_with_bbox(svc, tmp_path)
    report = svc.dry_run_export(aset_id, "labelme")
    assert report["lossless"] is True


def test_dry_run_xanylabeling_alias(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    aset_id, _ = _seed_with_bbox(svc, tmp_path)
    report = svc.dry_run_export(aset_id, "x-anylabeling")
    assert "lossless" in report


def test_dry_run_unsupported_format_raises(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    aset_id, _ = _seed_with_bbox(svc, tmp_path)
    with pytest.raises(ValueError, match="Unsupported"):
        svc.dry_run_export(aset_id, "nonexistent-format")


def test_dry_run_via_registry_dispatch(tmp_path: Path) -> None:
    """Confirm all 5 exportable formats accept dry_run without writing files."""
    svc = _service(tmp_path)
    aset_id, _ = _seed_with_bbox(svc, tmp_path)
    before = set(tmp_path.rglob("*"))
    for fmt in ("labelme", "x-anylabeling", "isat", "coco", "yolo-detection", "yolo-segmentation"):
        svc.dry_run_export(aset_id, fmt)
    after = set(tmp_path.rglob("*"))
    assert after == before, f"dry_run left files: {after - before}"
