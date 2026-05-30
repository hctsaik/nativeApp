from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from plugins.labeling.domain.services import AnnotationService
from plugins.labeling.domain.storage.workspace import AnnotationWorkspace
from plugins.labeling.mcp.handlers import AnnotationMCPHandlers


def _write_image(path: Path) -> None:
    Image.new("RGB", (20, 10), color=(10, 20, 30)).save(path)


def test_annotation_mcp_handler_happy_path(tmp_path: Path) -> None:
    image_path = tmp_path / "dog.png"
    _write_image(image_path)
    handlers = AnnotationMCPHandlers(AnnotationService(AnnotationWorkspace(tmp_path / "workspace")))

    dataset = json.loads(handlers.create_dataset("animals", str(tmp_path)))["data"]
    ingest = json.loads(handlers.ingest_assets(dataset["id"], json.dumps([str(image_path)])))["data"]
    asset = ingest["assets"][0]
    schema = json.loads(
        handlers.create_schema(
            "animals",
            json.dumps([{"id": "dog", "name": "dog", "allowed_geometry_types": ["bbox"]}]),
            schema_id="schema_1",
        )
    )["data"]
    annotation_set = json.loads(
        handlers.create_annotation_set(
            dataset["id"],
            schema["id"],
            json.dumps(
                [
                    {
                        "asset_id": asset["id"],
                        "label_id": "dog",
                        "geometry": {"type": "bbox", "x": 1, "y": 2, "width": 3, "height": 4},
                    }
                ]
            ),
        )
    )["data"]
    validation = json.loads(handlers.validate_set(annotation_set["id"]))
    task = json.loads(handlers.get_task(annotation_set["id"]))
    install = json.loads(handlers.detect_xanylabeling())

    assert validation["ok"] is True
    assert validation["data"]["ok"] is True
    assert task["data"]["task_id"] == annotation_set["id"]
    assert "available" in install["data"]


def test_annotation_mcp_handler_generic_format_tools(tmp_path: Path) -> None:
    image_path = tmp_path / "dog.png"
    _write_image(image_path)
    handlers = AnnotationMCPHandlers(AnnotationService(AnnotationWorkspace(tmp_path / "workspace")))

    dataset = json.loads(handlers.create_dataset("animals", str(tmp_path)))["data"]
    asset = json.loads(handlers.ingest_assets(dataset["id"], json.dumps([str(image_path)])))["data"]["assets"][0]
    schema = json.loads(
        handlers.create_schema(
            "animals",
            json.dumps([{"id": "dog", "name": "dog", "allowed_geometry_types": ["bbox", "polygon"]}]),
            schema_id="schema_1",
        )
    )["data"]
    annotation_set = json.loads(
        handlers.create_annotation_set(
            dataset["id"],
            schema["id"],
            json.dumps(
                [
                    {
                        "asset_id": asset["id"],
                        "label_id": "dog",
                        "geometry": {"type": "bbox", "x": 1, "y": 2, "width": 3, "height": 4},
                    }
                ]
            ),
        )
    )["data"]

    formats = json.loads(handlers.supported_annotation_formats())["data"]
    project = json.loads(
        handlers.prepare_labeling_project("isat", dataset["id"], schema["id"], str(tmp_path / "isat_project"))
    )["data"]
    export = json.loads(handlers.create_export(annotation_set["id"], "isat", str(tmp_path / "isat")))["data"]
    imported = json.loads(
        handlers.import_annotations(
            dataset["id"],
            schema["id"],
            "isat",
            str(tmp_path / "isat" / f"{asset['id']}.json"),
            asset_id=asset["id"],
        )
    )["data"]

    assert any(item["id"] == "isat" for item in formats)
    assert project["artifact_refs"]
    assert export["format"] == "isat"
    assert imported["annotation_set"]["provenance"]["adapter"] == "isat"


def test_annotation_mcp_handler_returns_structured_error(tmp_path: Path) -> None:
    handlers = AnnotationMCPHandlers(AnnotationService(AnnotationWorkspace(tmp_path / "workspace")))

    response = json.loads(handlers.get_schema("missing"))

    assert response["ok"] is False
    assert response["error"]["code"] == "NOT_FOUND"
