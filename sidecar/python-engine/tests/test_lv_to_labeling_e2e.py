"""E2E: LV object-level Export → Labeling workbench can read the boxes.

Pins the cross-component contract that was broken: LV's Export writes a YOLO
subset (images/ + labels/*.txt + classes.txt), but the annotation workbench
(module_012 / X-AnyLabeling) only renders boxes from a per-image sibling
``<image>.json``. The data-source step now seeds that JSON
(``plugins.labeling.domain.yolo_xany_seed``); these tests prove the boxes — and
their class NAMES — survive the LV→Labeling hop intact.

Hermetic: a tiny YOLO dataset is generated in ``tmp_path`` (no dependency on any
machine-specific dataset), exported via LV's real ``export_subset``, then seeded
via the real labeling helper.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ENGINE_ROOT = Path(__file__).resolve().parents[1]
_LV_SCRIPTS = _ENGINE_ROOT / "vendor" / "LV" / "scripts"
for _p in (str(_LV_SCRIPTS),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

try:
    import export_subset as es  # noqa: E402  (LV, via vendor/LV/scripts)
except Exception:  # pragma: no cover - LV submodule missing
    es = None

from plugins.labeling.domain import yolo_xany_seed as seed  # noqa: E402


# ── fixture: a tiny YOLO source dataset ──────────────────────────────────────
SRC_CLASSES = ["door", "window", "chair"]
# label rows per image: (class_id, cx, cy, w, h)
SRC_LABELS = {
    "a": [(2, 0.5, 0.5, 0.2, 0.2), (0, 0.3, 0.3, 0.1, 0.1)],
    "b": [(1, 0.6, 0.4, 0.3, 0.4)],
}


def _make_source(root: Path) -> Path:
    (root / "images").mkdir(parents=True)
    (root / "labels").mkdir(parents=True)
    (root / "classes.txt").write_text("\n".join(SRC_CLASSES) + "\n", encoding="utf-8")
    # distinct pixel content per image so sha256 dedup keeps both (a solid-colour
    # collision would merge them into one export item).
    fills = {"a": (200, 30, 30), "b": (30, 30, 200)}
    for stem, rows in SRC_LABELS.items():
        Image.new("RGB", (640, 480), fills.get(stem, (123, 222, 64))).save(
            root / "images" / f"{stem}.png")
        (root / "labels" / f"{stem}.txt").write_text(
            "\n".join(f"{c} {cx} {cy} {w} {h}" for c, cx, cy, w, h in rows) + "\n",
            encoding="utf-8")
    return root


def _expected_names_from_export(dst: Path) -> dict[str, list[str]]:
    """Recompute the expected per-image label NAMES from the exported subset
    (classes.txt rows index by remapped class id), so the assertion does not
    hard-code the remap LV chose."""
    classes = [c.strip() for c in (dst / "classes.txt").read_text(encoding="utf-8").splitlines() if c.strip()]
    out: dict[str, list[str]] = {}
    for lf in sorted((dst / "labels").glob("*.txt")):
        names = []
        for ln in lf.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                names.append(classes[int(float(ln.split()[0]))])
        out[lf.stem] = names
    return out


# ── the headline E2E ─────────────────────────────────────────────────────────
@pytest.mark.skipif(es is None, reason="LV submodule (vendor/LV) not present")
def test_lv_export_then_seed_yields_boxes_with_correct_class_names(tmp_path):
    src = _make_source(tmp_path / "src")
    dst = tmp_path / "out"

    items = []
    for stem in SRC_LABELS:
        ip = src / "images" / f"{stem}.png"
        items.append(es.ExportItem(
            image_path=ip,
            label_path=src / "labels" / f"{stem}.txt",
            class_names=list(SRC_CLASSES),
            source_tool="objcov",
            level="object",
            object_ids=[0],          # mimic "框選了某個物件"
            sha256=None,
        ))
    rep = es.export_subset(items, dst, mode="copy", layout="yolo", on_exists="overwrite")
    assert rep.exported == 2 and not rep.errors

    assert seed.looks_like_yolo_dir(dst) is True
    sr = seed.seed_xany_json_from_yolo(dst)
    # both images seeded, every box converted, no class fell off the palette
    assert sr.seeded == 2
    assert sr.boxes == sum(len(v) for v in SRC_LABELS.values()) == 3
    assert sr.warnings == []
    # the class list handed to the workbench == the exported palette (sorted union)
    assert sr.classes == sorted(SRC_CLASSES)

    expected = _expected_names_from_export(dst)
    for img in sorted((dst / "images").glob("*.png")):
        sidecar = img.with_suffix(".json")
        assert sidecar.exists(), f"no sibling json for {img.name}"
        d = json.loads(sidecar.read_text(encoding="utf-8"))
        w, h = Image.open(img).size
        assert (d["imageWidth"], d["imageHeight"]) == (w, h)
        assert d["imagePath"] == img.name
        got = [s["label"] for s in d["shapes"]]
        assert got == expected[img.stem], f"{img.name}: {got} != {expected[img.stem]}"
        for s in d["shapes"]:
            assert s["shape_type"] == "rectangle"
            (x1, y1), (x2, y2) = s["points"]
            assert 0 <= x1 <= x2 <= w and 0 <= y1 <= y2 <= h


# ── seed helper unit tests ───────────────────────────────────────────────────
def test_seed_reads_classes_from_data_yaml_when_no_classes_txt(tmp_path):
    root = _make_source(tmp_path / "ds")
    (root / "classes.txt").unlink()
    (root / "data.yaml").write_text(
        "path: .\nnc: 3\nnames:\n  - door\n  - window\n  - chair\n", encoding="utf-8")
    sr = seed.seed_xany_json_from_yolo(root)
    assert sr.classes == ["door", "window", "chair"]
    assert sr.seeded == 2


def test_seed_reads_inline_data_yaml_names(tmp_path):
    root = _make_source(tmp_path / "ds")
    (root / "classes.txt").unlink()
    (root / "data.yaml").write_text("names: ['door', 'window', 'chair']\n", encoding="utf-8")
    assert seed.read_classes(root) == ["door", "window", "chair"]


def test_seed_never_clobbers_existing_json(tmp_path):
    root = _make_source(tmp_path / "ds")
    existing = root / "images" / "a.json"
    existing.write_text('{"mine": true}', encoding="utf-8")
    sr = seed.seed_xany_json_from_yolo(root)            # default: no overwrite
    assert json.loads(existing.read_text(encoding="utf-8")) == {"mine": True}
    assert sr.skipped_exist == 1 and sr.seeded == 1


def test_seed_overwrite_true_replaces(tmp_path):
    root = _make_source(tmp_path / "ds")
    (root / "images" / "a.json").write_text('{"mine": true}', encoding="utf-8")
    sr = seed.seed_xany_json_from_yolo(root, overwrite=True)
    assert sr.seeded == 2
    d = json.loads((root / "images" / "a.json").read_text(encoding="utf-8"))
    assert "shapes" in d


def test_seed_out_of_range_class_id_kept_numeric_and_warned(tmp_path):
    root = _make_source(tmp_path / "ds")
    (root / "labels" / "a.txt").write_text("9 0.5 0.5 0.2 0.2\n", encoding="utf-8")  # 9 >= 3 names
    sr = seed.seed_xany_json_from_yolo(root)
    d = json.loads((root / "images" / "a.json").read_text(encoding="utf-8"))
    assert d["shapes"][0]["label"] == "9"
    assert any("class id 9" in w for w in sr.warnings)


def test_seed_handles_split_subfolder_layout(tmp_path):
    """LV Export of a split writes images/<split>/img + labels/<split>/img.txt
    (e.g. .../images/test/1003.png). The seeder must recurse and mirror the
    relative path to find each label, writing the sidecar next to the image."""
    root = tmp_path / "ds"
    (root / "images" / "test").mkdir(parents=True)
    (root / "labels" / "test").mkdir(parents=True)
    (root / "classes.txt").write_text("\n".join(SRC_CLASSES) + "\n", encoding="utf-8")
    for stem, rows in SRC_LABELS.items():
        Image.new("RGB", (640, 480), (10 + len(stem), 20, 30)).save(
            root / "images" / "test" / f"{stem}.png")
        (root / "labels" / "test" / f"{stem}.txt").write_text(
            "\n".join(f"{c} {cx} {cy} {w} {h}" for c, cx, cy, w, h in rows) + "\n",
            encoding="utf-8")

    assert seed.looks_like_yolo_dir(root) is True
    sr = seed.seed_xany_json_from_yolo(root)
    assert sr.seeded == 2 and sr.no_label == 0
    # sidecar written NEXT TO the image, inside the split subfolder
    for stem, rows in SRC_LABELS.items():
        js = root / "images" / "test" / f"{stem}.json"
        assert js.exists(), f"no sidecar for split image {stem}"
        d = json.loads(js.read_text(encoding="utf-8"))
        assert len(d["shapes"]) == len(rows)
        assert all(s["label"] in SRC_CLASSES for s in d["shapes"])


def test_looks_like_yolo_dir_false_without_labels(tmp_path):
    root = tmp_path / "plain"
    (root / "images").mkdir(parents=True)
    Image.new("RGB", (10, 10)).save(root / "images" / "x.png")
    assert seed.looks_like_yolo_dir(root) is False


# ── full data-source → workbench flow (the GUI path, headless) ───────────────
def _load_module_process(modid: str):
    """Load ``module_<id>/<id>_process.py`` the way the engine does."""
    import importlib.util
    p = _ENGINE_ROOT / "plugins" / "labeling" / "modules" / f"module_{modid}" / f"{modid}_process.py"
    spec = importlib.util.spec_from_file_location(f"_{modid}_process_e2e", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_data_source_to_workbench_sees_boxes_and_classes(tmp_path, monkeypatch):
    """module_026 (data source) → module_012 (workbench): pointing the data source
    at a YOLO subset must leave the workbench seeing every image as ANNOTATED
    (sibling .json present) with the dataset's class list — the exact regression
    behind 'Labeling 讀不到 Object 標記 / 類別名稱錯誤'."""
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "log"))
    src = _make_source(tmp_path / "ds")  # images + labels + classes.txt, no .json

    p026 = _load_module_process("026")
    p012 = _load_module_process("012")

    r26 = p026.execute_logic({"mode": "local", "folder_path": str(src), "recursive": True})
    assert r26["yolo_seed"]["applied"] is True
    assert r26["yolo_seed"]["seeded"] == 2
    manifest_id = r26["manifest_id"]

    cfg12 = json.loads((tmp_path / "log" / "config" / "module_012.json").read_text(encoding="utf-8"))
    labels = cfg12.get("annotation_labels")
    assert labels == SRC_CLASSES  # classes.txt order preserved (== class id order)

    r12 = p012.execute_logic({"manifest_id": manifest_id, "labels": labels,
                              "annotation_tool": "xanylabeling"})
    assert r12["mode"] == "ready"
    assert r12["total"] == 2
    assert r12["annotated"] == 2, "workbench must see both images as annotated"
    written = [c.strip() for c in Path(r12["classes_path"]).read_text(encoding="utf-8").splitlines() if c.strip()]
    assert written == SRC_CLASSES
