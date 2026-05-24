from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_021_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_help_spec = _ilu.spec_from_file_location("_help", _HERE.parent / "shared" / "_help.py")
_help = _ilu.module_from_spec(_help_spec)
_help_spec.loader.exec_module(_help)

# Relay script: forward cim:v1 messages from the nested iframe to the portal.
# The k8s app sends window.parent.postMessage({cim:'v1',...}) which arrives here
# (Streamlit output iframe). window.top sends it directly to portal-react.
_RELAY_JS = """
<script>
window.addEventListener('message', function(e) {
  if (e.data && e.data.cim === 'v1') {
    window.top.postMessage(e.data, '*');
  }
});
</script>
"""


def render_output(result: dict) -> None:
    _help.render_help_button("module_021", "output", "🔭 Vision DIY")

    if not result.get("success"):
        err = result.get("error", "")
        if err:
            st.error(f"載入失敗：{err}")
        else:
            url = _cfg.load_config().get("url", "")
            if url:
                _render_iframe(url)
            else:
                st.info("請在 Input 頁面填入 Web App URL，然後按「執行」。")
        return

    _render_iframe(result["url"])


def _render_iframe(url: str) -> None:
    # Inject relay JS (zero height — invisible, only for event forwarding)
    components.html(_RELAY_JS, height=0)

    # Full-viewport iframe (fills the Streamlit output area)
    st.markdown(
        f'<iframe src="{url}" '
        'style="width:100%;height:100vh;border:none;display:block;" '
        'allow="camera;microphone;clipboard-read;clipboard-write" '
        'referrerpolicy="no-referrer-when-downgrade">'
        '</iframe>',
        unsafe_allow_html=True,
    )
