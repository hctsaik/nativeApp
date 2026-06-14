"""Deterministic, self-contained fixtures for the LV (VisualLatent) BDD E2E suite.

Why this exists
---------------
LV's analysis tools are gated on (1) a model weight (``models/<name>.pth``) and
(2) a YOLO-layout dataset on disk. Neither is committed (weights are large; the
vendored submodule stays thin — see ``vendor/LV/README.md``). So the BDD suite
*generates* both at run time, deterministically, with zero network:

  * ``ensure_resnet18()`` writes a random-weight ``resnet18.pth`` into LV's
    model-house. ``ResNetExtractor`` loads it with ``strict=False`` and yields a
    real 512-D embedding per image — semantically meaningless but enough to drive
    the whole extract→reduce→scatter→cart pipeline end-to-end.
  * ``ensure_demo_dataset()`` writes a tiny multi-class YOLO dataset into
    ``vendor/LV/demo/coco8/{train,val}`` (the path LV's "▶ 一鍵體驗（coco8 範例）"
    button loads), including ONE image duplicated train→val so the near-duplicate /
    train-val-leakage scenario has a real positive to find.

All target paths are gitignored (``models/*.pth``, ``demo/``), so running the
suite never dirties version control. Everything is idempotent.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image

_LV_ROOT = Path(__file__).resolve().parents[3] / "vendor" / "LV"
MODELS_DIR = _LV_ROOT / "models"
DEMO_DIR = _LV_ROOT / "demo" / "coco8"
CLASSES = ["cat", "dog", "bird"]


# ── Model fixture ──────────────────────────────────────────────────────────────
def ensure_resnet18(seed: int = 0) -> Path:
    """Write a deterministic random-weight resnet18.pth into LV's model-house.

    ResNetExtractor does ``resnet18(weights=None)`` then
    ``load_state_dict(sd, strict=False)``, so a vanilla torchvision state_dict
    (random init) is a valid, loadable model that produces 512-D features.
    """
    import torch
    import torchvision.models as tvm

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    out = MODELS_DIR / "resnet18.pth"
    if out.exists():
        return out
    torch.manual_seed(seed)
    model = tvm.resnet18(weights=None)
    torch.save(model.state_dict(), str(out))
    return out


# ── Dataset fixture ─────────────────────────────────────────────────────────────
def _draw_image(cls_idx: int, variant: int, size: int = 64) -> Image.Image:
    """A small, class-distinct, deterministic image (base hue per class + a
    per-variant block) so different classes occupy different image regions."""
    rng = np.random.default_rng(cls_idx * 1000 + variant)
    base = np.zeros((size, size, 3), dtype=np.uint8)
    hue = [(200, 60, 60), (60, 180, 60), (60, 60, 200)][cls_idx % 3]
    base[:, :] = hue
    # a deterministic noisy patch so embeddings are not all identical
    patch = rng.integers(0, 255, (size // 2, size // 2, 3), dtype=np.uint8)
    y = (variant * 7) % (size // 2)
    base[y:y + size // 2, y:y + size // 2] = patch
    return Image.fromarray(base, "RGB")


def _write_split(split_dir: Path, items: list[tuple[int, int]]) -> None:
    """items = list of (cls_idx, variant). Writes images/ + YOLO labels/."""
    img_dir = split_dir / "images"
    lbl_dir = split_dir / "labels"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    for cls_idx, variant in items:
        name = f"{CLASSES[cls_idx]}_{variant:02d}"
        _draw_image(cls_idx, variant).save(img_dir / f"{name}.jpg", quality=92)
        # YOLO: one centered box of this class
        (lbl_dir / f"{name}.txt").write_text(
            f"{cls_idx} 0.5 0.5 0.4 0.4\n", encoding="utf-8")


def ensure_demo_dataset() -> dict:
    """Create demo/coco8/{train,val} YOLO dataset + classes.txt.

    Returns a dict describing the fixture: paths, counts, the sha256 of the
    deliberately duplicated (train→val leakage) image so tests can assert it.
    Idempotent: re-running with the fixture present is a no-op.
    """
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    (DEMO_DIR / "classes.txt").write_text("\n".join(CLASSES) + "\n", encoding="utf-8")

    # train: 4 per class across 3 classes = 12 images
    train_items = [(c, v) for c in range(3) for v in range(4)]
    # val: 2 per class = 6 images, with DIFFERENT variants from train
    val_items = [(c, v) for c in range(3) for v in (10, 11)]

    train_dir = DEMO_DIR / "train"
    val_dir = DEMO_DIR / "val"
    _write_split(train_dir, train_items)
    _write_split(val_dir, val_items)

    # Inject a train→val leakage duplicate: copy one train image byte-for-byte
    # into val so phash/sha256 near-duplicate detection has a real positive.
    src = train_dir / "images" / "cat_00.jpg"
    dup = val_dir / "images" / "cat_00_LEAK.jpg"
    dup.write_bytes(src.read_bytes())
    (val_dir / "labels" / "cat_00_LEAK.txt").write_text(
        "0 0.5 0.5 0.4 0.4\n", encoding="utf-8")
    leak_sha = hashlib.sha256(src.read_bytes()).hexdigest()

    return {
        "demo_dir": DEMO_DIR,
        "train_dir": train_dir,
        "val_dir": val_dir,
        "classes": CLASSES,
        "n_train": len(train_items),
        "n_val": len(val_items) + 1,  # + the leak dup
        "leak_sha256": leak_sha,
        "leak_pair": ("train/images/cat_00.jpg", "val/images/cat_00_LEAK.jpg"),
    }


def ensure_all() -> dict:
    model = ensure_resnet18()
    ds = ensure_demo_dataset()
    ds["model_pth"] = model
    ds["model_name"] = "resnet18"
    return ds


if __name__ == "__main__":
    info = ensure_all()
    print("[fixtures] model :", info["model_pth"], "exists:", info["model_pth"].exists())
    print("[fixtures] demo  :", info["demo_dir"])
    print("[fixtures] train :", info["n_train"], "val:", info["n_val"])
    print("[fixtures] leak  :", info["leak_pair"], "sha256=", info["leak_sha256"][:12], "…")
