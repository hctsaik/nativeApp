"""Streamlit runner for embedded full external apps (``runner: bi`` → tools/bi_runner.py).

Launches the AI4BI Streamlit application. AI4BI is developed in its own repo and
vendored as a git submodule at ``sidecar/python-engine/vendor/AI4BI``, installed
editable into the engine's Python — so updating AI4BI is just a ``git pull`` in
the submodule (the editable install reflects immediately) and this thin runner
rarely needs to change.

The engine runs this via ``streamlit run tools/bi_runner.py`` as a single-pane
'app' tool (see ToolProcessManager._start_app). We execute ``ai4bi/ui/app.py``
exactly as ``python -m ai4bi.ui.app`` would, so its
``if __name__ == "__main__": main()`` guard fires under Streamlit and the app
owns the whole page (its own st.set_page_config / layout / sidebar).
"""
from __future__ import annotations

import runpy

runpy.run_module("ai4bi.ui.app", run_name="__main__")
