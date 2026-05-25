"""
示範外部系統如何將圖片與標注資料打包成 CIM 平台規定的 ZIP 格式。

ZIP 內部結構（COCO 格式）：
  images/
    *.jpg / *.png
  annotations.json   （COCO 格式）

ZIP 內部結構（YOLO 格式）：
  images/
    *.jpg / *.png
  labels/
    *.txt            （每行: class_id cx cy w h，均為 0~1 正規化座標）

使用方式：
  python payload_builder.py
  → 自動在 sample_data/zips/ 產生示範 ZIP 檔

或在程式中呼叫：
  from payload_builder import build_coco_zip, build_yolo_zip
"""

import io
import json
import zipfile
from pathlib import Path


# ─── COCO ZIP 打包 ────────────────────────────────────────────────────────────


def build_coco_zip(
    images_dir: Path,
    coco_json: dict,
    output_path: Path,
) -> None:
    """
    將指定目錄中的圖片與 COCO JSON 標注打包成 ZIP。

    Args:
        images_dir:   含有 *.jpg / *.png 的目錄
        coco_json:    符合 COCO 格式的 dict（必須包含 images、annotations、categories）
        output_path:  輸出 ZIP 的完整路徑（例如 sample_data/zips/TASK_001.zip）

    ZIP 結構：
        images/
            <圖片檔名>
        annotations.json
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 打包所有圖片
        image_count = 0
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp"):
            for img_path in sorted(images_dir.glob(ext)):
                zf.write(img_path, arcname=f"images/{img_path.name}")
                image_count += 1

        if image_count == 0:
            raise ValueError(f"images_dir 中找不到任何圖片：{images_dir}")

        # 打包 COCO JSON
        zf.writestr(
            "annotations.json",
            json.dumps(coco_json, ensure_ascii=False, indent=2),
        )

    print(f"[COCO ZIP] 已建立：{output_path}（{image_count} 張圖片）")


# ─── YOLO ZIP 打包 ────────────────────────────────────────────────────────────


def build_yolo_zip(
    images_dir: Path,
    labels_dir: Path,
    output_path: Path,
    class_names: list[str] | None = None,
) -> None:
    """
    將圖片目錄與 YOLO 標注目錄打包成 ZIP。

    Args:
        images_dir:   含有 *.jpg / *.png 的目錄
        labels_dir:   含有對應 *.txt 標注的目錄
                      每行格式：class_id cx cy w h（0~1 正規化）
        output_path:  輸出 ZIP 的完整路徑
        class_names:  類別名稱列表，若提供則一併寫入 classes.txt

    ZIP 結構：
        images/
            <圖片檔名>
        labels/
            <標注 txt 檔名>
        classes.txt  （若提供 class_names）
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 打包所有圖片
        image_count = 0
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp"):
            for img_path in sorted(images_dir.glob(ext)):
                zf.write(img_path, arcname=f"images/{img_path.name}")
                image_count += 1

        if image_count == 0:
            raise ValueError(f"images_dir 中找不到任何圖片：{images_dir}")

        # 打包對應的 YOLO 標注 txt
        label_count = 0
        for txt_path in sorted(labels_dir.glob("*.txt")):
            zf.write(txt_path, arcname=f"labels/{txt_path.name}")
            label_count += 1

        # 選擇性寫入類別名稱
        if class_names:
            zf.writestr("classes.txt", "\n".join(class_names))

    print(
        f"[YOLO ZIP] 已建立：{output_path}"
        f"（{image_count} 張圖片，{label_count} 個標注）"
    )


# ─── 示範用輔助：在記憶體產生測試圖片 ───────────────────────────────────────


def _make_test_png_bytes(width: int = 64, height: int = 64, color: tuple = (128, 200, 128)) -> bytes:
    """在記憶體中產生純色測試 PNG，不依賴外部檔案。"""
    try:
        from PIL import Image

        img = Image.new("RGB", (width, height), color=color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        # Pillow 未安裝：回傳最小合法 PNG
        import base64

        b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVQI12NgAAAAAgAB4iG8MwAAAABJRU5ErkJggg=="
        return base64.b64decode(b64)


def _build_demo_zip_in_memory(task_id: str = "TASK_DEMO") -> bytes:
    """
    完全在記憶體中建立示範 ZIP，不需要任何外部圖片目錄。
    適合單元測試或 CI 環境使用。
    """
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 寫入兩張測試圖
        zf.writestr("images/sample_01.png", _make_test_png_bytes(64, 64, (200, 200, 200)))
        zf.writestr("images/sample_02.png", _make_test_png_bytes(64, 64, (100, 150, 200)))

        # 寫入 COCO 標注
        coco = {
            "info": {"description": f"示範任務 {task_id}", "version": "1.0"},
            "images": [
                {"id": 1, "file_name": "sample_01.png", "width": 64, "height": 64},
                {"id": 2, "file_name": "sample_02.png", "width": 64, "height": 64},
            ],
            "categories": [
                {"id": 1, "name": "defect"},
                {"id": 2, "name": "scratch"},
            ],
            "annotations": [
                {
                    "id": 1,
                    "image_id": 1,
                    "category_id": 1,
                    "bbox": [10, 10, 20, 20],
                    "area": 400,
                    "iscrowd": 0,
                }
            ],
        }
        zf.writestr("annotations.json", json.dumps(coco, ensure_ascii=False, indent=2))

    return buf.getvalue()


# ─── Demo 主程式 ──────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import tempfile

    output_dir = Path(__file__).parent / "sample_data" / "zips"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=== payload_builder.py 示範 ===\n")

    # 示範一：直接在記憶體建立 ZIP 並寫到磁碟
    print("[示範 1] 記憶體內建立 COCO ZIP（不需要外部圖片目錄）")
    demo_zip_bytes = _build_demo_zip_in_memory("TASK_DEMO")
    demo_zip_path = output_dir / "TASK_DEMO.zip"
    demo_zip_path.write_bytes(demo_zip_bytes)
    print(f"  → 已寫出：{demo_zip_path}（{len(demo_zip_bytes):,} bytes）\n")

    # 示範二：用臨時目錄模擬真實圖片目錄的打包流程
    print("[示範 2] 從圖片目錄 + COCO JSON 打包")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        images_dir = tmp_path / "images"
        images_dir.mkdir()

        # 寫入臨時測試圖
        (images_dir / "img_001.png").write_bytes(_make_test_png_bytes(64, 64, (255, 100, 0)))
        (images_dir / "img_002.png").write_bytes(_make_test_png_bytes(64, 64, (0, 100, 255)))

        coco_json = {
            "info": {"description": "從目錄打包示範"},
            "images": [
                {"id": 1, "file_name": "img_001.png", "width": 64, "height": 64},
                {"id": 2, "file_name": "img_002.png", "width": 64, "height": 64},
            ],
            "categories": [{"id": 1, "name": "defect"}],
            "annotations": [],
        }

        coco_zip_path = output_dir / "TASK_COCO_DEMO.zip"
        build_coco_zip(images_dir, coco_json, coco_zip_path)

    # 示範三：YOLO 格式打包
    print("\n[示範 3] 從圖片目錄 + YOLO labels 打包")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        images_dir = tmp_path / "images"
        labels_dir = tmp_path / "labels"
        images_dir.mkdir()
        labels_dir.mkdir()

        (images_dir / "img_001.png").write_bytes(_make_test_png_bytes())
        # YOLO 格式：class_id cx cy w h（0~1 正規化）
        (labels_dir / "img_001.txt").write_text("0 0.5 0.5 0.3 0.3\n", encoding="utf-8")

        yolo_zip_path = output_dir / "TASK_YOLO_DEMO.zip"
        build_yolo_zip(
            images_dir,
            labels_dir,
            yolo_zip_path,
            class_names=["defect", "scratch"],
        )

    print("\n所有示範 ZIP 已建立於：", output_dir)
