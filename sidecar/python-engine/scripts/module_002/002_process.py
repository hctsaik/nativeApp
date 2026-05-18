from __future__ import annotations

import os
from pathlib import Path

from PIL import Image


def execute_logic(params: dict) -> dict:
    image_path = params["image_path"]
    memo = params.get("memo", "")

    with Image.open(image_path) as img:
        width, height = img.size

    file_size_bytes = os.path.getsize(image_path)
    file_size_kb = round(file_size_bytes / 1024, 2)

    return {
        "filename": Path(image_path).name,
        "resolution": (width, height),
        "file_size_bytes": file_size_bytes,
        "file_size_kb": file_size_kb,
        "memo": memo,
    }
