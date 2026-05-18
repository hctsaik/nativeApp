"""
手動整合測試腳本：Platform annotation-core → X-AnyLabeling GUI 串接驗證

用法：
    python scripts/test_xanylabeling_integration.py [--launch] [--image PATH] [--out DIR]

    --launch      準備完 project folder 後實際啟動 X-AnyLabeling GUI
    --image PATH  指定自訂圖片（省略則用 sample 圖）
    --out DIR     輸出目錄（預設 tmp/xany-integration-test）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "sidecar" / "python-engine"))

from annotation.adapters.xanylabeling_runtime import detect_xanylabeling
from annotation.services import AnnotationService
from annotation.storage.workspace import AnnotationWorkspace

try:
    from PIL import Image, ImageDraw
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_sample_images(out: Path) -> list[Path]:
    """Generate two simple RGB sample images for testing."""
    if not _HAS_PIL:
        raise RuntimeError("Pillow is required. pip install Pillow")
    images: list[Path] = []
    specs = [
        ("sample_dog.png", (245, 247, 250), (114, 150, 196)),
        ("sample_cat.png", (250, 245, 240), (196, 150, 114)),
    ]
    for name, bg, fg in specs:
        path = out / name
        img = Image.new("RGB", (320, 240), color=bg)
        draw = ImageDraw.Draw(img)
        draw.ellipse((80, 60, 240, 180), fill=fg, outline=(40, 60, 100), width=3)
        draw.rectangle((130, 170, 190, 230), fill=fg, outline=(40, 60, 100), width=2)
        img.save(path)
        images.append(path)
    return images


def _print_section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def _check(label: str, ok: bool, detail: str = "") -> None:
    mark = "OK" if ok else "FAIL"
    line = f"  [{mark}] {label}"
    if detail:
        line += f"  ({detail})"
    print(line)
    if not ok:
        sys.exit(1)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--launch", action="store_true", help="啟動 X-AnyLabeling GUI")
    parser.add_argument("--image", default="", help="自訂圖片路徑")
    parser.add_argument("--out", default=str(REPO / "tmp" / "xany-integration-test"), help="輸出目錄")
    args = parser.parse_args()

    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)
    print(f"\n輸出目錄：{root}")

    # ── 1. 偵測 X-AnyLabeling ─────────────────────────────────────────────────
    _print_section("1. 偵測 X-AnyLabeling 安裝")
    install = detect_xanylabeling()
    _check("X-AnyLabeling 可用", install.available, install.message)
    print(f"     executable : {install.executable}")
    print(f"     version    : {install.version}")
    print(f"     source     : {install.source}")

    # ── 2. 準備圖片 ───────────────────────────────────────────────────────────
    _print_section("2. 準備測試圖片")
    source_dir = root / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    if args.image and Path(args.image).exists():
        import shutil
        target = source_dir / Path(args.image).name
        shutil.copy2(args.image, target)
        image_paths = [target]
        print(f"     使用自訂圖片：{target}")
    else:
        image_paths = _make_sample_images(source_dir)
        print(f"     生成 sample 圖片：{[p.name for p in image_paths]}")

    for p in image_paths:
        _check(p.name, p.exists(), f"{p.stat().st_size} bytes")

    # ── 3. annotation-core：建立 dataset + schema + annotations ──────────────
    _print_section("3. annotation-core 流程")
    service = AnnotationService(AnnotationWorkspace(root / "workspace"))

    dataset = service.create_dataset("xany-integration-test", str(root))
    _check("create_dataset", bool(dataset.get("id")), dataset["id"])

    ingest = service.ingest_assets(dataset["id"], [str(p) for p in image_paths])
    assets = ingest["assets"]
    _check("ingest_assets", len(assets) == len(image_paths), f"{len(assets)} assets")

    schema = service.create_schema(
        "integration-schema",
        [
            {"id": "dog", "name": "dog", "allowed_geometry_types": ["bbox", "polygon"]},
            {"id": "cat", "name": "cat", "allowed_geometry_types": ["bbox", "polygon"]},
            {"id": "other", "name": "other", "allowed_geometry_types": ["bbox"]},
        ],
    )
    _check("create_schema", bool(schema.get("id")), f"{len(schema['labels'])} labels")

    # 為第一張圖建立一個 bbox annotation
    first_asset = assets[0]
    annotation_set = service.create_annotation_set(
        dataset["id"],
        schema["id"],
        [
            {
                "asset_id": first_asset["id"],
                "label_id": "dog",
                "geometry": {"type": "bbox", "x": 80, "y": 60, "width": 160, "height": 120},
                "attributes": {"quality": "good"},
            }
        ],
        created_by="integration-test",
    )
    _check("create_annotation_set", bool(annotation_set.get("id")), annotation_set["state"])

    validation = service.validate_set(annotation_set["id"])
    _check("validate_set", validation.get("ok") is True, str(validation.get("errors", [])))

    # ── 4. 準備 X-AnyLabeling project folder ─────────────────────────────────
    _print_section("4. 準備 X-AnyLabeling project folder")
    xany_dir = root / "xany_project"
    xany_result = service.prepare_xanylabeling_project(dataset["id"], schema["id"], str(xany_dir))
    _check("prepare_xanylabeling_project", bool(xany_result))

    # 驗證 project folder 結構
    manifest_path = xany_dir / "manifest.json"
    classes_path = xany_dir / "classes.txt"
    images_dir = xany_dir / "images"
    labels_dir = xany_dir / "labels"

    _check("manifest.json 存在", manifest_path.exists())
    _check("classes.txt 存在", classes_path.exists())
    _check("images/ 目錄存在", images_dir.exists())
    _check("labels/ 目錄存在", labels_dir.exists())

    classes = classes_path.read_text(encoding="utf-8").strip().splitlines()
    _check("classes.txt 內容正確", set(classes) == {"dog", "cat", "other"}, str(classes))

    images_copied = list(images_dir.glob("*"))
    _check(f"圖片已複製到 images/", len(images_copied) == len(image_paths), f"{len(images_copied)} 個檔案")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _check("manifest dataset_id 正確", manifest["dataset_id"] == dataset["id"])

    print(f"\n  Project folder 內容：")
    print(f"    manifest.json : {json.dumps(manifest, ensure_ascii=False, indent=2)[:300]}...")
    print(f"    classes.txt   : {classes}")
    print(f"    images/       : {[p.name for p in images_copied]}")

    # ── 5. 啟動 X-AnyLabeling GUI ─────────────────────────────────────────────
    _print_section("5. 啟動 X-AnyLabeling GUI")
    if args.launch:
        launch = service.launch_xanylabeling_project(str(xany_dir))
        _check("launch 成功", launch.get("launched") is True)
        print(f"     command : {' '.join(str(c) for c in launch['command'])}")
        print("\n  X-AnyLabeling 已在背景啟動。")
        print("  請在 GUI 中驗證：")
        print("   - 左側顯示 images/ 中的圖片")
        print("   - 右側 Labels 面板顯示 dog / cat / other")
        print("   - 標注後會自動儲存到 labels/ 資料夾")
        print(f"\n  project folder：{xany_dir}")
    else:
        print("  （略過，請加 --launch 參數以實際啟動 GUI）")
        print(f"\n  手動啟動指令：")
        exe = install.executable
        print(f"    {exe} --filename \"{images_dir}\" --output \"{labels_dir}\" --work-dir \"{xany_dir / '.xanylabeling'}\" --nodata --autosave --no-auto-update-check --labels \"{classes_path}\" --validatelabel exact")

    # ── 6. 摘要 ──────────────────────────────────────────────────────────────
    _print_section("6. 測試摘要")
    print(f"  全部檢查通過。")
    print(f"  輸出目錄：{root}")
    print(f"  X-AnyLabeling project：{xany_dir}")
    if not args.launch:
        print(f"\n  提示：重新執行時加上 --launch 以實際啟動 GUI。")


if __name__ == "__main__":
    main()
