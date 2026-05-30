from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_mcp_configs_point_to_current_repo() -> None:
    root_config = _load(REPO_ROOT / ".mcp.json")
    claude_config = _load(REPO_ROOT / ".claude" / "mcp.json")

    expected_repo = str(REPO_ROOT).replace("\\", "/")
    root_text = json.dumps(root_config)
    claude_text = json.dumps(claude_config)

    # Verify configs reference the current repo's path (not hardcoded to another machine)
    assert expected_repo in root_text, f"Expected {expected_repo!r} in .mcp.json"
    assert expected_repo in claude_text, f"Expected {expected_repo!r} in .claude/mcp.json"


def test_mcp_config_paths_exist() -> None:
    root_config = _load(REPO_ROOT / ".mcp.json")
    claude_config = _load(REPO_ROOT / ".claude" / "mcp.json")

    for server in root_config["mcpServers"].values():
        pythonpath = server.get("env", {}).get("PYTHONPATH", "")
        for part in pythonpath.split(";"):
            if part:
                assert Path(part).exists(), part

    for server in claude_config["mcpServers"].values():
        if "cwd" in server:
            assert Path(server["cwd"]).exists(), server["cwd"]


def test_packaged_sidecar_source_includes_management_dependencies() -> None:
    package = _load(REPO_ROOT / "apps" / "host-electron" / "package.json")
    source_resource = next(
        item for item in package["build"]["extraResources"]
        if item.get("to") == "sidecar-source"
    )
    filters = set(source_resource["filter"])

    assert "management_insights.py" in filters
    assert "management_package_importer.py" in filters
    assert "management_schema.py" in filters
    assert "management_store.py" in filters
    assert "management_use_cases.py" in filters
    # platform-level packages added during Platform-First refactor
    assert "plugins/**/*" in filters  # Labeling plugin home (P6: annotation domain → plugins/labeling/domain)
    assert "core/**/*" in filters  # platform core (P5→P6: cim_platform fully replaced by core.integrations)
    assert "sheets/**/*" in filters
    assert "scripts/**/*" in filters


def test_pyinstaller_engine_includes_management_dependencies() -> None:
    spec_text = (REPO_ROOT / "sidecar" / "python-engine" / "engine.spec").read_text(encoding="utf-8")

    assert "'management_insights'" in spec_text
    assert "'management_package_importer'" in spec_text
    assert "'management_schema'" in spec_text
    assert "'management_store'" in spec_text
    assert "'management_use_cases'" in spec_text
