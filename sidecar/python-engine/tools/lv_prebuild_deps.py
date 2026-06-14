"""Out-of-band pre-build of the per-tool venv for the LV ('app-lv') app.

LV declares 14 heavy `requires:` (torch==2.6.0, transformers, umap-learn, …).
The engine builds this venv lazily on first launch via
`_prewarm_deps_and_timeout` → `core.tool_deps.ensure_tool_deps`, which blocks the
whole `/tools/app-lv/start` request through a multi-GB pip install.

Running this script up-front builds the *same* venv (same path
`<engine_root>/.tool-venvs/app-lv`, same version-independent fingerprint), so the
engine's later prewarm hits the fingerprint and returns instantly — making the
real launch (and the E2E harness) fast and deterministic. Re-running is a no-op
once the fingerprint matches.

Usage (from repo root, with a real Python that has venv + Tcl/Tk):
    py -3.11 sidecar/python-engine/tools/lv_prebuild_deps.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import yaml

_ENGINE_ROOT = Path(__file__).resolve().parents[1]  # sidecar/python-engine
sys.path.insert(0, str(_ENGINE_ROOT))

from core.tool_deps import ensure_tool_deps, tool_venv_dir  # noqa: E402

_PLUGIN_YAML = _ENGINE_ROOT / "plugins" / "lv" / "modules" / "app-lv" / "plugin.yaml"


def main() -> int:
    data = yaml.safe_load(_PLUGIN_YAML.read_text(encoding="utf-8")) or {}
    requires = [str(r) for r in (data.get("requires") or []) if str(r).strip()]
    print(f"[lv-prebuild] tool=app-lv requires={len(requires)} items")
    for r in requires:
        print(f"             - {r}")
    print(f"[lv-prebuild] target venv: {tool_venv_dir('app-lv')}")
    print("[lv-prebuild] building (first run downloads torch et al; may take 10-20 min)…")
    t0 = time.time()
    result = ensure_tool_deps("app-lv", requires)
    dt = round(time.time() - t0, 1)
    print(f"[lv-prebuild] done in {dt}s ok={result.ok}")
    print(f"[lv-prebuild] message: {result.message}")
    print(f"[lv-prebuild] venv_dir: {result.venv_dir}")
    print(f"[lv-prebuild] site_packages: {result.site_packages}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
