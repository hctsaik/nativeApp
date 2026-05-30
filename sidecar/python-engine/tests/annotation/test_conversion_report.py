from __future__ import annotations

import pytest

from plugins.labeling.domain.core.models import ConversionReport, LossEntry


def test_lossentry_fields() -> None:
    e = LossEntry(loss_type="dropped", field="geometry", reason="bbox not supported")
    assert e.loss_type == "dropped"
    assert e.field == "geometry"
    assert e.severity == "warning"
    assert e.asset_id is None


def test_report_summary_lossless() -> None:
    r = ConversionReport()
    assert r.build_summary() == "lossless"


def test_report_summary_warnings() -> None:
    r = ConversionReport()
    r.add_loss("approximated", "geometry", "bbox converted to polygon", severity="warning")
    assert "warning" in r.build_summary()
    assert r.lossless is False


def test_report_summary_errors() -> None:
    r = ConversionReport()
    r.add_loss("unsupported", "rle_mask", "RLE not supported", severity="error")
    assert "error" in r.build_summary()


def test_add_loss_updates_legacy_fields() -> None:
    r = ConversionReport()
    r.add_loss("dropped", "rotation", "Rotation field dropped")
    assert "rotation" in r.dropped_fields
    assert len(r.warnings) > 0
    assert r.lossless is False


def test_add_loss_approximated_updates_approximated_fields() -> None:
    r = ConversionReport()
    r.add_loss("approximated", "segmentation", "bbox approximated as polygon")
    assert "segmentation" in r.approximated_fields


def test_add_loss_unsupported_updates_unsupported_annotations() -> None:
    r = ConversionReport()
    r.add_loss("unsupported", "rle", "RLE unsupported")
    assert "rle" in r.unsupported_annotations


def test_backwards_compat_no_losses_field() -> None:
    # Old code that constructs ConversionReport without new fields
    r = ConversionReport(lossless=False, dropped_fields=["rotation"])
    d = r.to_dict()
    assert "losses" in d
    assert "mapping_version" in d
    assert "summary" in d
    assert d["losses"] == []


def test_mark_loss_still_works() -> None:
    r = ConversionReport()
    r.mark_loss("deprecated_field", "field was removed")
    assert r.lossless is False
    assert "deprecated_field" in r.dropped_fields


def test_to_dict_includes_summary() -> None:
    r = ConversionReport()
    r.add_loss("dropped", "field", "reason")
    d = r.to_dict()
    assert d["summary"] != ""
    assert "warning" in d["summary"] or "error" in d["summary"]


def test_mapping_version_persists() -> None:
    r = ConversionReport(mapping_version="v1.2")
    assert r.to_dict()["mapping_version"] == "v1.2"
