from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .base import PullConnector, PushConnector
from ..models import AnnotationPayload, FetchedItem, PushResult

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def _md5_prefix(path: Path, length: int = 16) -> str | None:
    try:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:length]
    except Exception:
        return None


class LocalFileConnector(PullConnector, PushConnector):
    """
    Default connector that reads images from a local directory and writes
    X-AnyLabeling JSON annotation files alongside the images.

    Activated automatically when no connector.yaml is present.
    Behaviour is identical to the pre-connector module implementations.
    """

    def __init__(
        self,
        source_dir: str | Path = "",
        extensions: set[str] | None = None,
        recursive: bool = False,
    ) -> None:
        self._source_dir = Path(source_dir) if source_dir else Path()
        self._extensions = extensions or _IMAGE_EXTENSIONS
        self._recursive = recursive
        self._items: list[FetchedItem] | None = None  # lazy-scanned cache

    # ── PullConnector ─────────────────────────────────────────────────────────

    def _scan(self) -> list[FetchedItem]:
        if self._items is not None:
            return self._items
        if not self._source_dir or not self._source_dir.is_dir():
            self._items = []
            return self._items

        glob = self._source_dir.rglob("*") if self._recursive else self._source_dir.iterdir()
        items: list[FetchedItem] = []
        for fp in sorted(glob):
            if not fp.is_file():
                continue
            if fp.suffix.lower() not in self._extensions:
                continue
            abs_path = str(fp.resolve())
            try:
                from PIL import Image as _PILImage
                with _PILImage.open(abs_path) as img:
                    w, h = img.width, img.height
            except Exception:
                w = h = None
            items.append(FetchedItem(
                item_id=uuid4().hex,
                file_path=abs_path,
                image_url=None,
                width=w,
                height=h,
                file_hash=_md5_prefix(fp),
                metadata={},
            ))
        self._items = items
        return items

    def fetch_page(self, offset: int, limit: int) -> list[FetchedItem]:
        all_items = self._scan()
        return all_items[offset: offset + limit]

    def resolve_image(self, item: FetchedItem, local_dir: Path) -> Path:
        # Local files are already on disk; return the path as-is.
        return Path(item.file_path)

    # ── PushConnector ─────────────────────────────────────────────────────────

    def push_batch(self, payloads: list[AnnotationPayload]) -> list[PushResult]:
        """
        Write X-AnyLabeling JSON alongside each image.
        This is the local-file equivalent of "pushing" annotation results.
        """
        results: list[PushResult] = []
        for p in payloads:
            try:
                img_path = Path(p.image_path)
                ann_path = img_path.with_suffix(".json")
                data = {
                    "version": "1.0.0",
                    "flags": {
                        **({"classification": p.classification} if p.classification else {}),
                        **({"confidence": p.confidence} if p.confidence is not None else {}),
                    },
                    "shapes": p.shapes,
                    "imagePath": img_path.name,
                    "imageData": None,
                    "imageHeight": p.image_height,
                    "imageWidth": p.image_width,
                }
                tmp = ann_path.with_suffix(".tmp")
                tmp.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                os.replace(tmp, ann_path)
                results.append(PushResult(p.item_id, True, str(ann_path), None))
            except Exception as exc:
                results.append(PushResult(p.item_id, False, None, str(exc)))
        return results

    def check_remote_version(self, item_ids: list[str]) -> dict[str, str]:
        # Local files have no remote version; return empty dict.
        return {}
