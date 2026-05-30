from __future__ import annotations

import pytest

from plugins.labeling.domain.formats.contracts import FormatCapabilities, FormatDescriptor
from plugins.labeling.domain.formats.registry import FormatRegistry, get_format_registry, reset_format_registry


# ── Helpers ──────────────────────────────────────────────────────────────────


def _fresh() -> FormatRegistry:
    r = FormatRegistry()

    class _NoopAdapter:
        def export(self, *a, **k): pass
        def import_file(self, *a, **k): pass
        def import_dir(self, *a, **k): pass

    caps = FormatCapabilities()
    r.register(FormatDescriptor("foo", "Foo Format", caps, aliases=["foo-json", "foo_json"]), _NoopAdapter())
    r.register(FormatDescriptor("bar", "Bar Format", FormatCapabilities(requires_asset=False)), _NoopAdapter())
    return r


# ── Unit tests ────────────────────────────────────────────────────────────────


def test_register_and_get_by_id() -> None:
    r = _fresh()
    desc, _ = r.get("foo")
    assert desc.format_id == "foo"
    assert desc.display_name == "Foo Format"


def test_get_by_alias_normalizes() -> None:
    r = _fresh()
    desc, _ = r.get("foo-json")
    assert desc.format_id == "foo"
    desc2, _ = r.get("foo_json")
    assert desc2.format_id == "foo"


def test_unknown_format_raises_value_error() -> None:
    r = _fresh()
    with pytest.raises(ValueError, match="Unsupported"):
        r.get("nonexistent")


def test_coco_requires_asset_false() -> None:
    reset_format_registry()
    reg = get_format_registry()
    desc, _ = reg.get("coco")
    assert desc.capabilities.requires_asset is False


def test_list_supported_shape_matches_legacy() -> None:
    reset_format_registry()
    reg = get_format_registry()
    formats = reg.list_supported()
    # Same 6 formats as the old hardcoded list
    ids = {f["id"] for f in formats}
    assert ids == {"labelme", "x-anylabeling", "isat", "coco", "yolo-detection", "yolo-segmentation"}
    for f in formats:
        assert "id" in f
        assert "name" in f
        assert "can_import" in f
        assert "can_export" in f


def test_all_builtins_registered() -> None:
    reset_format_registry()
    reg = get_format_registry()
    for fid in ("labelme", "x-anylabeling", "isat", "coco", "yolo-detection", "yolo-segmentation"):
        desc, adapter = reg.get(fid)
        assert desc.format_id == fid


def test_xanylabeling_alias() -> None:
    reset_format_registry()
    reg = get_format_registry()
    desc, _ = reg.get("xanylabeling")
    assert desc.format_id == "x-anylabeling"


def test_yolo_aliases() -> None:
    reset_format_registry()
    reg = get_format_registry()
    assert reg.get("yolo-seg")[0].format_id == "yolo-segmentation"
    assert reg.get("yolo-detect")[0].format_id == "yolo-detection"
    assert reg.get("yolo")[0].format_id == "yolo-detection"


def test_lossless_roundtrip_labelme_xany() -> None:
    reset_format_registry()
    reg = get_format_registry()
    for fid in ("labelme", "x-anylabeling"):
        desc, _ = reg.get(fid)
        assert desc.capabilities.lossless_roundtrip is True


def test_lossless_roundtrip_false_for_lossy() -> None:
    reset_format_registry()
    reg = get_format_registry()
    for fid in ("isat", "coco", "yolo-detection", "yolo-segmentation"):
        desc, _ = reg.get(fid)
        assert desc.capabilities.lossless_roundtrip is False


def test_normalize_underscore_to_dash() -> None:
    reset_format_registry()
    reg = get_format_registry()
    assert reg.normalize("yolo_detection") == "yolo-detection"
    assert reg.normalize("yolo_segmentation") == "yolo-segmentation"
