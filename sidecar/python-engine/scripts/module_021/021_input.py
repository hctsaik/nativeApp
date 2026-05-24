from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_021_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_help_spec = _ilu.spec_from_file_location("_help", _HERE.parent / "shared" / "_help.py")
_help = _ilu.module_from_spec(_help_spec)
_help_spec.loader.exec_module(_help)


def render_input() -> dict:
    _help.render_help_button("module_021", "input", "🔭 Vision DIY")
    st.caption("設定要嵌入的外部 Web App 網址（必須是 HTTPS），按下「執行」後 Output 頁面會顯示該應用程式。")

    cfg = _cfg.load_config()
    saved_url = cfg.get("url", "")

    url = st.text_input(
        "Web App URL *",
        value=st.session_state.get("m021_url", saved_url),
        key="m021_url",
        placeholder="https://your-k8s-app.example.com",
    )

    if url and not url.startswith("https://"):
        st.warning("⚠️ URL 必須以 `https://` 開頭，否則 Electron 可能拒絕載入。")
    elif not url.strip():
        st.info("請填入 Web App URL 後按下「執行」。")

    if url != saved_url:
        cfg["url"] = url
        _cfg.save_config(cfg)

    return {"url": url.strip()}
