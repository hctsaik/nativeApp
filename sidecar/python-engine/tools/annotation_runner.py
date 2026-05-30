"""
annotation_runner — runner for module_009 (統一標注平台).

Loads and executes 009_runner.py as a single-page Streamlit app.
Unlike cv_framework_runner, there is no Input/Output split — both
CIM_TOOL_LAYER=input and CIM_TOOL_LAYER=output render the same full UI.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_ENGINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ENGINE_DIR))

TOOL_ID = os.environ.get("CIM_TOOL_ID", "module_009")
MODULE_ID = os.environ.get("CIM_MODULE_ID", "009")

# Resolve the module folder across scripts/ AND plugins/*/modules/ (the Labeling
# GUI modules moved to plugins/labeling/modules/ in the platform restructure).
try:
    from plugin_loader import find_module_folder  # noqa: PLC0415
    _module_dir = find_module_folder(f"module_{MODULE_ID}")
except Exception:
    _module_dir = _ENGINE_DIR / "scripts" / f"module_{MODULE_ID}"
_runner_path = _module_dir / f"{MODULE_ID}_runner.py"

if not _runner_path.exists():
    import streamlit as st
    st.error(f"Runner script not found: {_runner_path}")
else:
    sys.path.insert(0, str(_runner_path.parent))
    spec = importlib.util.spec_from_file_location("_module_runner", _runner_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
