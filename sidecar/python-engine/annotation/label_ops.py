from __future__ import annotations

"""
label_ops.py — Global label operations across X-AnyLabeling JSON files.

All file writes use the tmp + os.replace atomic pattern so an interrupted
operation never leaves a file in a partially-written state.
"""

import difflib
import json
import os
from pathlib import Path


def scan_labels(items: list[dict]) -> dict[str, list[str]]:
    """
    Scan all X-AnyLabeling JSON sidecars for the given manifest items.

    Returns {label: [file_path, ...]} covering both shapes[].label and
    flags.classification.  Labels that appear only in flags are included.
    """
    label_to_files: dict[str, list[str]] = {}

    for it in items:
        fp = it.get("file_path", "")
        if not fp:
            continue
        ann = Path(fp).with_suffix(".json")
        if not ann.exists():
            continue
        try:
            data = json.loads(ann.read_text(encoding="utf-8"))
        except Exception:
            continue

        seen: set[str] = set()
        for s in data.get("shapes", []):
            lbl = s.get("label", "")
            if lbl:
                seen.add(lbl)
        clf = data.get("flags", {}).get("classification", "")
        if clf:
            seen.add(clf)

        for lbl in seen:
            label_to_files.setdefault(lbl, [])
            if fp not in label_to_files[lbl]:
                label_to_files[lbl].append(fp)

    return label_to_files


def find_near_duplicates(
    labels: list[str],
    threshold: float = 0.8,
) -> list[tuple[str, str, float]]:
    """
    Return (label_a, label_b, ratio) pairs where ratio > threshold and < 1.0.
    Used to surface potential typos like "Cat" / "cat" / "CAT".
    """
    pairs: list[tuple[str, str, float]] = []
    for i, a in enumerate(labels):
        for b in labels[i + 1:]:
            ratio = difflib.SequenceMatcher(None, a, b).ratio()
            if threshold < ratio < 1.0:
                pairs.append((a, b, round(ratio, 3)))
    return pairs


def _rewrite_file(path: Path, transform) -> bool:
    """
    Read a JSON file, apply transform(data) → data, write atomically.
    Returns True if the file was changed, False if transform returned None.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False

    result = transform(data)
    if result is None:
        return False

    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return True


def rename_label(items: list[dict], old: str, new: str) -> int:
    """
    Rename label `old` to `new` across all annotation files in the manifest.

    Applies to both shapes[].label and flags.classification.
    Returns the number of files modified.
    """
    if not old or not new or old == new:
        return 0

    count = 0
    for it in items:
        fp = it.get("file_path", "")
        if not fp:
            continue
        ann = Path(fp).with_suffix(".json")
        if not ann.exists():
            continue

        def _rename(data: dict, _old=old, _new=new) -> dict | None:
            changed = False
            for s in data.get("shapes", []):
                if s.get("label") == _old:
                    s["label"] = _new
                    changed = True
            flags = data.get("flags", {})
            if flags.get("classification") == _old:
                flags["classification"] = _new
                changed = True
            return data if changed else None

        if _rewrite_file(ann, _rename):
            count += 1

    return count


def merge_labels(items: list[dict], sources: list[str], target: str) -> int:
    """
    Merge all labels in `sources` into `target`.
    Returns total number of files modified.
    """
    total = 0
    for src in sources:
        if src != target:
            total += rename_label(items, src, target)
    return total


def delete_label(items: list[dict], label: str) -> int:
    """
    Remove all shapes with the given label and clear flags.classification
    when it equals label.

    Returns the number of files modified.
    """
    if not label:
        return 0

    count = 0
    for it in items:
        fp = it.get("file_path", "")
        if not fp:
            continue
        ann = Path(fp).with_suffix(".json")
        if not ann.exists():
            continue

        def _delete(data: dict, _lbl=label) -> dict | None:
            original_len = len(data.get("shapes", []))
            data["shapes"] = [s for s in data.get("shapes", []) if s.get("label") != _lbl]
            changed = len(data["shapes"]) != original_len
            flags = data.get("flags", {})
            if flags.get("classification") == _lbl:
                flags["classification"] = ""
                changed = True
            return data if changed else None

        if _rewrite_file(ann, _delete):
            count += 1

    return count
