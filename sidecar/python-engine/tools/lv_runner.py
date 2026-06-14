"""Streamlit runner for the LV / VisualLatent embedded app (``runner: lv`` → tools/lv_runner.py).

LV (dataset curation / embedding analysis) is developed in its own repo and
vendored as a git submodule at ``sidecar/python-engine/vendor/LV``. Unlike AI4BI
(a proper installable package), LV is a *flat* ``scripts/`` app —
``scripts/app.py`` imports sibling modules (``from interaction import …``) — so
this runner puts LV's ``scripts/`` dir on ``sys.path`` and runpy-executes
``app.py`` as ``__main__``, exactly as ``streamlit run scripts/app.py`` would.
Its ``if __name__ == "__main__": main()`` guard fires under Streamlit and the app
owns the whole page (its own st.set_page_config / layout / sidebar).

The ``sys.path`` insert lives only in THIS Streamlit subprocess (the engine spawns
one process per ``app`` tool, see ToolProcessManager._start_app), so LV's generic
module names (interaction / models / manifest) can't leak into or clash with other
plugins' processes.

Updating LV is just a ``git pull`` in the submodule — this thin runner rarely
changes. Model weights are NOT vendored (the submodule stays thin); the platform
points LV at a writable model-house via ``LV_MODELS_DIR`` / ``LV_INCEPTION_DIR``
(LV reads those env vars; unset → its local ``models/`` default).
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

_LV_ROOT = Path(__file__).resolve().parent.parent / "vendor" / "LV"
_LV_SCRIPTS = _LV_ROOT / "scripts"

# Default the model-house to the submodule's own models/ unless the platform has
# already pointed LV elsewhere (kept here so a plain dev checkout "just runs"
# once weights are dropped in vendor/LV/models).
import os  # noqa: E402

os.environ.setdefault("LV_MODELS_DIR", str(_LV_ROOT / "models"))
os.environ.setdefault("LV_INCEPTION_DIR", str(_LV_ROOT / "model"))

if str(_LV_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_LV_SCRIPTS))

runpy.run_path(str(_LV_SCRIPTS / "app.py"), run_name="__main__")
