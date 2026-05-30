"""
MCP stdio client test for annotation_mcp server.

Starts the annotation MCP server as a subprocess, sends JSON-RPC 2.0 messages,
and verifies the complete round-trip:
  create_dataset -> ingest_assets -> create_schema -> create_task ->
  prepare_xanylabeling_project -> detect_xanylabeling ->
  (simulate X-AnyLabeling output) ->
  import_xanylabeling_project_labels ->
  validate_set -> submit_for_review -> review_task -> create_export

Usage:
    python scripts/test_annotation_mcp.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MCP_DIR = REPO / "mcp"
SIDECAR_DIR = REPO / "sidecar" / "python-engine"
WORKSPACE = REPO / "tmp" / "mcp-test-workspace"

PYTHONPATH = f"{MCP_DIR};{SIDECAR_DIR}"
ENV = {**os.environ, "PYTHONPATH": PYTHONPATH, "ANNOTATION_WORKSPACE": str(WORKSPACE)}


# ── MCP stdio client ──────────────────────────────────────────────────────────

class MCPClient:
    def __init__(self, proc: subprocess.Popen) -> None:
        self._proc = proc
        self._id = 0

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _send(self, msg: dict) -> None:
        line = json.dumps(msg, ensure_ascii=False) + "\n"
        self._proc.stdin.write(line.encode())
        self._proc.stdin.flush()

    def _recv(self) -> dict:
        while True:
            raw = self._proc.stdout.readline()
            if not raw:
                raise RuntimeError("MCP server closed stdout unexpectedly")
            raw = raw.strip()
            if not raw:
                continue
            return json.loads(raw)

    def initialize(self) -> dict:
        req_id = self._next_id()
        self._send({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mcp-test-client", "version": "0.1"},
            },
        })
        resp = self._recv()
        # send initialized notification
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        return resp

    def call_tool(self, name: str, arguments: dict) -> dict:
        req_id = self._next_id()
        self._send({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        resp = self._recv()
        if "error" in resp:
            raise RuntimeError(f"MCP error calling {name}: {resp['error']}")
        content = resp.get("result", {}).get("content", [])
        text = content[0]["text"] if content else "{}"
        return json.loads(text)

    def close(self) -> None:
        try:
            self._proc.stdin.close()
            self._proc.wait(timeout=5)
        except Exception:
            self._proc.kill()


# ── helpers ───────────────────────────────────────────────────────────────────

def _check(label: str, ok: bool, detail: str = "") -> None:
    mark = "OK  " if ok else "FAIL"
    line = f"  [{mark}] {label}"
    if detail:
        line += f"  ({detail})"
    print(line)
    if not ok:
        sys.exit(1)


def _print_section(title: str) -> None:
    print(f"\n{'─' * 64}")
    print(f"  {title}")
    print(f"{'─' * 64}")


def _unwrap(resp: dict) -> dict:
    """Return resp['data'] and assert ok=True."""
    assert resp.get("ok") is True, f"Response not ok: {resp}"
    return resp["data"]


def _make_sample_image(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (200, 150), color=color)
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), path.name, fill=(0, 0, 0))
    img.save(path)


def _make_labelme_json(image_name: str, width: int, height: int, labels: list[dict]) -> dict:
    """Simulate X-AnyLabeling output for one image."""
    shapes = []
    for label in labels:
        shapes.append({
            "label": label["label"],
            "points": [[label["x1"], label["y1"]], [label["x2"], label["y2"]]],
            "group_id": None,
            "description": "",
            "shape_type": "rectangle",
            "flags": {},
        })
    return {
        "version": "5.0.1",
        "flags": {"classification_labels": []},
        "shapes": shapes,
        "imagePath": image_name,
        "imageData": None,
        "imageHeight": height,
        "imageWidth": width,
    }


# ── test sequence ─────────────────────────────────────────────────────────────

def run_tests(client: MCPClient) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="mcp-xany-"))
    xany_project_dir = str(tmp / "xany_project")
    export_dir = str(tmp / "exports")

    # ── 1. prepare sample images ──────────────────────────────────────────────
    _print_section("0. Prepare sample images")
    img_a = tmp / "img_a.png"
    img_b = tmp / "img_b.png"
    _make_sample_image(img_a, color=(200, 210, 220))
    _make_sample_image(img_b, color=(220, 200, 180))
    _check("img_a.png created", img_a.exists())
    _check("img_b.png created", img_b.exists())

    # ── 2. create_dataset ─────────────────────────────────────────────────────
    _print_section("1. annotation_create_dataset")
    resp = client.call_tool("annotation_create_dataset", {
        "name": "mcp-test-dataset",
        "root_uri": str(tmp),
        "metadata_json": "{}",
    })
    data = _unwrap(resp)
    dataset_id = data["id"]
    _check("dataset created", bool(dataset_id), dataset_id)

    # ── 3. ingest_assets ──────────────────────────────────────────────────────
    _print_section("2. annotation_ingest_assets")
    resp = client.call_tool("annotation_ingest_assets", {
        "dataset_id": dataset_id,
        "image_paths_json": json.dumps([str(img_a), str(img_b)]),
        "copy": True,
    })
    data = _unwrap(resp)
    assets = data["assets"]
    _check("2 assets ingested", len(assets) == 2, f"{len(assets)}")
    asset_a = assets[0]
    asset_b = assets[1]

    # ── 4. create_schema ──────────────────────────────────────────────────────
    _print_section("3. annotation_create_schema")
    labels = [
        {"id": "cat", "name": "cat", "allowed_geometry_types": ["bbox", "polygon"]},
        {"id": "dog", "name": "dog", "allowed_geometry_types": ["bbox", "polygon"]},
    ]
    resp = client.call_tool("annotation_create_schema", {
        "name": "mcp-test-schema",
        "labels_json": json.dumps(labels),
    })
    data = _unwrap(resp)
    schema_id = data["id"]
    _check("schema created", bool(schema_id), f"{len(data['labels'])} labels")

    # ── 5. create_task (empty annotation set) ─────────────────────────────────
    _print_section("4. annotation_create_task")
    resp = client.call_tool("annotation_create_task", {
        "dataset_id": dataset_id,
        "schema_id": schema_id,
        "annotations_json": "[]",
        "created_by": "mcp-test",
    })
    data = _unwrap(resp)
    aset_id_initial = data["id"]
    _check("task created", bool(aset_id_initial), data["state"])

    # ── 6. detect_xanylabeling ────────────────────────────────────────────────
    _print_section("5. annotation_detect_xanylabeling")
    resp = client.call_tool("annotation_detect_xanylabeling", {})
    data = _unwrap(resp)
    _check("X-AnyLabeling detected", data.get("available") is True, data.get("version", "?"))
    print(f"     exe     : {data.get('executable')}")
    print(f"     version : {data.get('version')}")

    # ── 7. prepare_xanylabeling_project ───────────────────────────────────────
    _print_section("6. annotation_prepare_xanylabeling_project")
    resp = client.call_tool("annotation_prepare_xanylabeling_project", {
        "dataset_id": dataset_id,
        "schema_id": schema_id,
        "output_dir": xany_project_dir,
        "asset_ids_json": "null",
    })
    data = _unwrap(resp)
    xany_root = Path(xany_project_dir)
    _check("project folder created", (xany_root / "manifest.json").exists())
    _check("classes.txt written", (xany_root / "classes.txt").exists())
    classes = (xany_root / "classes.txt").read_text(encoding="utf-8").strip().splitlines()
    _check("classes correct", set(classes) == {"cat", "dog"}, str(classes))
    copied = list((xany_root / "images").glob("*.png"))
    _check("images copied", len(copied) == 2, f"{len(copied)} files")

    # ── 8. simulate X-AnyLabeling labeling output ─────────────────────────────
    _print_section("7. Simulate X-AnyLabeling label output")
    labels_dir = xany_root / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)

    payload_a = _make_labelme_json("img_a.png", 200, 150, [
        {"label": "cat", "x1": 10, "y1": 10, "x2": 80, "y2": 70},
    ])
    payload_b = _make_labelme_json("img_b.png", 200, 150, [
        {"label": "dog", "x1": 20, "y1": 20, "x2": 120, "y2": 100},
        {"label": "cat", "x1": 130, "y1": 30, "x2": 190, "y2": 90},
    ])
    (labels_dir / "img_a.json").write_text(json.dumps(payload_a), encoding="utf-8")
    (labels_dir / "img_b.json").write_text(json.dumps(payload_b), encoding="utf-8")
    _check("img_a.json written", (labels_dir / "img_a.json").exists())
    _check("img_b.json written", (labels_dir / "img_b.json").exists())
    print("     (simulating X-AnyLabeling saved 1+2 bbox annotations)")

    # ── 9. import_xanylabeling_project_labels (NEW tool) ─────────────────────
    _print_section("8. annotation_import_xanylabeling_project_labels  [NEW]")
    resp = client.call_tool("annotation_import_xanylabeling_project_labels", {
        "dataset_id": dataset_id,
        "schema_id": schema_id,
        "labels_dir": str(labels_dir),
    })
    data = _unwrap(resp)
    imported_aset_id = data["annotation_set"]["id"]
    matched = data["matched_count"]
    unmatched = data["unmatched_files"]
    _check("import OK", bool(imported_aset_id), imported_aset_id)
    _check("3 annotations imported", matched == 3, f"{matched}")
    _check("no unmatched files", unmatched == [], str(unmatched))
    print(f"     annotation_set_id : {imported_aset_id}")
    print(f"     matched count     : {matched}")

    # ── 10. validate_set ──────────────────────────────────────────────────────
    _print_section("9. annotation_validate_set")
    resp = client.call_tool("annotation_validate_set", {"annotation_set_id": imported_aset_id})
    data = _unwrap(resp)
    _check("validation passed", data.get("ok") is True, str(data.get("issues", [])))

    # ── 11. submit_for_review ─────────────────────────────────────────────────
    _print_section("10. annotation_submit_for_review")
    resp = client.call_tool("annotation_submit_for_review", {"annotation_set_id": imported_aset_id})
    data = _unwrap(resp)
    _check("state = submitted", data.get("state") == "submitted", data.get("state"))

    # ── 12. review_task (approve) ─────────────────────────────────────────────
    _print_section("11. annotation_review_task (approved)")
    resp = client.call_tool("annotation_review_task", {
        "annotation_set_id": imported_aset_id,
        "decision": "approved",
        "actor_id": "mcp-reviewer",
        "comment": "MCP integration test approval",
    })
    data = _unwrap(resp)
    state = data["annotation_set"]["state"]
    _check("state = approved", state == "approved", state)

    # ── 13. create_export (coco) ──────────────────────────────────────────────
    _print_section("12. annotation_create_export (coco, training)")
    resp = client.call_tool("annotation_create_export", {
        "annotation_set_id": imported_aset_id,
        "export_format": "coco",
        "output_dir": export_dir + "/coco",
        "purpose": "training",
    })
    data = _unwrap(resp)
    export_id = data.get("export_id", "")
    _check("export_id returned", bool(export_id), export_id)
    coco_path = Path(export_dir) / "coco" / "annotations.json"
    _check("annotations.json written", coco_path.exists())

    coco = json.loads(coco_path.read_text(encoding="utf-8"))
    ann_count = len(coco.get("annotations", []))
    _check("3 COCO annotations", ann_count == 3, f"{ann_count}")
    cat_count = len(coco.get("categories", []))
    _check("2 categories", cat_count == 2, f"{cat_count}")

    # ── 14. get_export ────────────────────────────────────────────────────────
    _print_section("13. annotation_get_export")
    resp = client.call_tool("annotation_get_export", {"export_id": export_id})
    data = _unwrap(resp)
    _check("export record retrieved", data.get("export_id") == export_id)

    # ── 15. list_tasks ────────────────────────────────────────────────────────
    _print_section("14. annotation_list_tasks")
    resp = client.call_tool("annotation_list_tasks", {"dataset_id": dataset_id})
    data = _unwrap(resp)
    _check("tasks listed", isinstance(data, list) and len(data) >= 1, f"{len(data)} tasks")

    # ── summary ───────────────────────────────────────────────────────────────
    _print_section("Summary")
    print("  All MCP tool calls passed.")
    print(f"  dataset_id        : {dataset_id}")
    print(f"  schema_id         : {schema_id}")
    print(f"  annotation_set_id : {imported_aset_id}")
    print(f"  COCO export       : {coco_path}")
    print(f"  tmp dir           : {tmp}")


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    print("Starting annotation MCP server...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "annotation_mcp.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=ENV,
        cwd=str(MCP_DIR),
    )

    client = MCPClient(proc)
    try:
        resp = client.initialize()
        server_info = resp.get("result", {}).get("serverInfo", {})
        print(f"  server: {server_info.get('name')} {server_info.get('version', '')}")
        run_tests(client)
    finally:
        client.close()
        stderr = proc.stderr.read().decode(errors="replace")
        if stderr.strip():
            print("\n--- server stderr ---")
            print(stderr[:2000])


if __name__ == "__main__":
    main()
