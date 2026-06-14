"""Submodule preflight guard tests.

When the project is obtained via GitHub "Download ZIP" or cloned without
``--recurse-submodules``, the labeling / AI4BI submodule dirs are empty and the
plugin/sheet scans (which glob those dirs) silently match nothing — tools vanish
from the catalog with no error. ``engine.check_submodules`` /
``engine.preflight_submodules`` turn that silent failure into a loud, pasteable
``[CIM-PREFLIGHT]`` signal (engine.log) and surface it via ``/diagnostics`` so the
cause + fix is one paste away.
"""
from __future__ import annotations

import logging

import engine


def _sentinel(id_, name, sub, repo, path, kind="submodule",
              fix="git submodule update --init --recursive"):
    return {"id": id_, "name": name, "kind": kind, "submodule": sub, "repo": repo,
            "sentinel": path, "fix": fix}


def test_check_submodules_clean_when_sentinels_present():
    # The repo under test has both submodules checked out (dev/CI invariant),
    # so a real check returns no missing entries.
    assert engine.check_submodules() == []


def test_check_submodules_detects_only_the_missing_one(monkeypatch, tmp_path):
    present = tmp_path / "present.py"
    present.write_text("ok", encoding="utf-8")
    fake = (
        _sentinel("labeling", "影像標註 (Labeling)", "plugins/labeling",
                  "ANnoTation", tmp_path / "absent" / "plugin.manifest.yaml",
                  kind="external", fix="scripts\\win\\link-labeling.bat"),
        _sentinel("ai4bi", "AI Report (AI4BI)", "vendor/AI4BI", "AI4BI", present),
    )
    monkeypatch.setattr(engine, "_SUBMODULE_SENTINELS", fake)

    missing = engine.check_submodules()
    assert {m["id"] for m in missing} == {"labeling"}
    entry = missing[0]
    assert entry["submodule"] == "plugins/labeling"
    assert entry["repo"] == "ANnoTation"
    # Labeling is now an external plugin (junction), not a git submodule — its fix
    # is the junction setup script, NOT `git submodule update`.
    assert entry["kind"] == "external"
    assert "link-labeling" in entry["fix"]


def test_ai4bi_missing_reports_git_submodule_fix(monkeypatch, tmp_path):
    present = tmp_path / "present.yaml"
    present.write_text("ok", encoding="utf-8")
    fake = (
        _sentinel("labeling", "影像標註 (Labeling)", "plugins/labeling",
                  "ANnoTation", present, kind="external",
                  fix="scripts\\win\\link-labeling.bat"),
        _sentinel("ai4bi", "AI Report (AI4BI)", "vendor/AI4BI", "AI4BI",
                  tmp_path / "absent" / "app.py"),
    )
    monkeypatch.setattr(engine, "_SUBMODULE_SENTINELS", fake)

    missing = engine.check_submodules()
    assert {m["id"] for m in missing} == {"ai4bi"}
    assert missing[0]["kind"] == "submodule"
    assert missing[0]["fix"] == "git submodule update --init --recursive"


def test_check_submodules_skipped_in_frozen_build(monkeypatch, tmp_path):
    # Packaged builds bundle submodule content differently; sentinel paths N/A.
    fake = (_sentinel("labeling", "x", "plugins/labeling", "ANnoTation",
                      tmp_path / "nope.yaml"),)
    monkeypatch.setattr(engine, "_SUBMODULE_SENTINELS", fake)
    monkeypatch.setattr(engine.sys, "frozen", True, raising=False)
    assert engine.check_submodules() == []


def test_preflight_logs_greppable_actionable_error(monkeypatch, tmp_path, caplog):
    fake = (_sentinel("labeling", "影像標註 (Labeling)", "plugins/labeling",
                      "ANnoTation", tmp_path / "nope.yaml",
                      kind="external", fix="scripts\\win\\link-labeling.bat"),)
    monkeypatch.setattr(engine, "_SUBMODULE_SENTINELS", fake)

    with caplog.at_level(logging.ERROR):
        missing = engine.preflight_submodules()

    assert len(missing) == 1
    messages = [r.getMessage() for r in caplog.records]
    # The marker must be greppable so the user can paste it to an AI assistant.
    assert any("[CIM-PREFLIGHT]" in m for m in messages)
    # The per-entry fix must appear verbatim so the user can act on it.
    assert any("link-labeling" in m for m in messages)


def test_preflight_silent_when_all_present(caplog):
    # Real (checked-out) sentinels → no error logging, empty result. Proves the
    # guard does not cry wolf on a correctly installed tree.
    with caplog.at_level(logging.ERROR):
        missing = engine.preflight_submodules()
    assert missing == []
    assert not any("[CIM-PREFLIGHT]" in r.getMessage() for r in caplog.records)
