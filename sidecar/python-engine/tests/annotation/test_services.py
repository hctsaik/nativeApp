from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from annotation.core.errors import ConflictError
from annotation.services import AnnotationService
from annotation.storage.workspace import AnnotationWorkspace


def _write_image(path: Path) -> None:
    Image.new("RGB", (100, 80), color=(1, 2, 3)).save(path)


def _service(tmp_path: Path) -> AnnotationService:
    return AnnotationService(AnnotationWorkspace(tmp_path / "workspace"))


def _seed(service: AnnotationService, tmp_path: Path) -> tuple[str, str, str, str]:
    image_path = tmp_path / "dog.png"
    _write_image(image_path)
    dataset = service.create_dataset("animals", str(tmp_path))
    asset = service.ingest_assets(dataset["id"], [str(image_path)])["assets"][0]
    schema = service.create_schema(
        "animals",
        [
            {"id": "dog", "name": "dog", "allowed_geometry_types": ["bbox"]},
        ],
        schema_id="schema_1",
    )
    annotation_set = service.create_annotation_set(
        dataset["id"],
        schema["id"],
        [
            {
                "asset_id": asset["id"],
                "label_id": "dog",
                "geometry": {"type": "bbox", "x": 10, "y": 20, "width": 30, "height": 40},
            }
        ],
    )
    return dataset["id"], asset["id"], schema["id"], annotation_set["id"]


def test_service_review_approval_blocks_later_overwrite(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _, asset_id, _, annotation_set_id = _seed(service, tmp_path)

    service.submit_for_review(annotation_set_id)
    service.review_task(annotation_set_id, "approved", actor_id="reviewer")

    with pytest.raises(ConflictError):
        service.upsert_annotations(
            annotation_set_id,
            [
                {
                    "asset_id": asset_id,
                    "label_id": "dog",
                    "geometry": {"type": "bbox", "x": 1, "y": 2, "width": 3, "height": 4},
                }
            ],
        )


def test_training_export_requires_approved_annotation_set(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _, _, _, annotation_set_id = _seed(service, tmp_path)

    with pytest.raises(ConflictError):
        service.create_export(annotation_set_id, "yolo-detection", str(tmp_path / "yolo"), purpose="training")

    service.submit_for_review(annotation_set_id)
    service.review_task(annotation_set_id, "approved", actor_id="reviewer")
    result = service.create_export(annotation_set_id, "yolo-detection", str(tmp_path / "yolo"), purpose="training")

    assert result["format"] == "yolo-detection"
    assert result["conversion_report"]["lossless"] is True
    assert (tmp_path / "yolo" / "manifest.json").exists()
    assert service.get_export(result["export_id"])["export_id"] == result["export_id"]


def test_service_lists_mvp_tasks(tmp_path: Path) -> None:
    service = _service(tmp_path)
    dataset_id, _, _, annotation_set_id = _seed(service, tmp_path)

    tasks = service.list_tasks(dataset_id)
    task = service.get_task(annotation_set_id)

    assert tasks[0]["task_id"] == annotation_set_id
    assert task["annotation_set"]["id"] == annotation_set_id


def test_service_imports_labelme_as_new_annotation_set(tmp_path: Path) -> None:
    service = _service(tmp_path)
    dataset_id, asset_id, schema_id, annotation_set_id = _seed(service, tmp_path)
    service.create_export(annotation_set_id, "labelme", str(tmp_path / "labelme"))

    imported = service.import_xanylabeling_annotations(
        dataset_id,
        schema_id,
        asset_id,
        str(tmp_path / "labelme" / f"{asset_id}.json"),
    )

    assert imported["annotation_set"]["id"] != annotation_set_id
    assert imported["conversion_report"]["warnings"] == []


def test_service_lists_supported_annotation_formats(tmp_path: Path) -> None:
    service = _service(tmp_path)

    formats = service.supported_annotation_formats()
    by_id = {item["id"]: item for item in formats}

    assert by_id["labelme"]["can_import"] is True
    assert by_id["x-anylabeling"]["can_export"] is True
    assert by_id["isat"]["can_import"] is True
    assert by_id["coco"]["can_import"] is True
    assert by_id["yolo-segmentation"]["can_export"] is True


def test_service_create_export_dispatches_isat_and_yolo_segmentation(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _, _, _, annotation_set_id = _seed(service, tmp_path)

    isat = service.create_export(annotation_set_id, "isat", str(tmp_path / "isat"))
    yolo_seg = service.create_export(annotation_set_id, "yolo-seg", str(tmp_path / "yolo_seg"))

    assert isat["format"] == "isat"
    assert (tmp_path / "isat" / "conversion_report.json").exists()
    assert yolo_seg["format"] == "yolo-seg"
    assert (tmp_path / "yolo_seg" / "classes.txt").exists()


def test_service_generic_imports_isat_file(tmp_path: Path) -> None:
    service = _service(tmp_path)
    dataset_id, asset_id, schema_id, annotation_set_id = _seed(service, tmp_path)
    service.create_export(annotation_set_id, "isat", str(tmp_path / "isat"))

    imported = service.import_annotations(
        dataset_id,
        schema_id,
        "isat",
        str(tmp_path / "isat" / f"{asset_id}.json"),
        asset_id=asset_id,
    )

    assert imported["annotation_set"]["id"] != annotation_set_id
    assert imported["annotation_set"]["provenance"]["adapter"] == "isat"


def test_service_imports_yolo_detection_project_labels(tmp_path: Path) -> None:
    service = _service(tmp_path)
    dataset_id, asset_id, schema_id, _ = _seed(service, tmp_path)
    labels_dir = tmp_path / "yolo_labels"
    labels_dir.mkdir()
    (labels_dir / f"{asset_id}.txt").write_text("0 0.250000 0.500000 0.300000 0.500000\n", encoding="utf-8")

    imported = service.import_project_labels(dataset_id, schema_id, "yolo-detect", str(labels_dir))

    assert imported["annotation_set"]["provenance"]["adapter"] == "yolo-detection"
    assert imported["matched_count"] == 1


def test_service_prepare_xanylabeling_project(tmp_path: Path) -> None:
    service = _service(tmp_path)
    dataset_id, _, schema_id, _ = _seed(service, tmp_path)

    result = service.prepare_xanylabeling_project(dataset_id, schema_id, str(tmp_path / "xany"))
    manifest = json.loads((tmp_path / "xany" / "manifest.json").read_text(encoding="utf-8"))

    assert result["artifact_refs"]
    assert manifest["dataset_id"] == dataset_id
    assert (tmp_path / "xany" / "classes.txt").exists()


def test_service_prepare_labeling_project_dispatches_isat(tmp_path: Path) -> None:
    service = _service(tmp_path)
    dataset_id, _, schema_id, _ = _seed(service, tmp_path)

    result = service.prepare_labeling_project("isat", dataset_id, schema_id, str(tmp_path / "isat_project"))
    manifest = json.loads((tmp_path / "isat_project" / "manifest.json").read_text(encoding="utf-8"))

    assert result["artifact_refs"]
    assert manifest["adapter"] == "isat"
    assert (tmp_path / "isat_project" / "images").exists()
    assert (tmp_path / "isat_project" / "categories.txt").exists()


def test_service_detect_xanylabeling_shape(tmp_path: Path) -> None:
    service = _service(tmp_path)

    install = service.detect_xanylabeling()

    assert "available" in install
    assert "message" in install
