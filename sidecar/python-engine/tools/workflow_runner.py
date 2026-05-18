from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import streamlit as st

_ENGINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ENGINE_DIR))

from auth_provider import AuthProvider  # noqa: E402
from plugin_loader import PluginLoader  # noqa: E402
from plugin_registry import PluginRegistry  # noqa: E402

LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", "/tmp"))
WORKFLOW_ID = os.environ.get("CIM_WORKFLOW_ID", "")
_LAYER = os.environ.get("CIM_TOOL_LAYER", "input")

_DB_PATH = Path(os.environ.get("CIM_TOOLS_DB", str(LOG_DIR / "data" / "tools.sqlite")))


def _registry() -> PluginRegistry:
    return PluginRegistry(db_path=_DB_PATH, scripts_dir=_ENGINE_DIR / "scripts")


def _auth() -> AuthProvider:
    return AuthProvider(db_path=_DB_PATH)


def _wf_key(plugin_id: str) -> str:
    return f"wf_result_{WORKFLOW_ID}_{plugin_id}"


def _prev_result(plugin_id: str, steps: list) -> dict | None:
    """Return the result of the step that comes before plugin_id, if any."""
    for i, step in enumerate(steps):
        if step.plugin_id == plugin_id and i > 0:
            return st.session_state.get(_wf_key(steps[i - 1].plugin_id))
    return None


def render_step(step, steps: list) -> None:
    try:
        input_mod = PluginLoader.load_module(step.plugin_id, "input")
    except Exception as exc:
        st.error(f"載入 {step.plugin_id} input 失敗：{exc}")
        return

    # If there's a result from the previous step, surface it via session_state
    # so the input module can optionally read it
    prev = _prev_result(step.plugin_id, steps)
    if prev:
        st.session_state[f"wf_prev_{step.plugin_id}"] = prev
        with st.expander("使用前一步驟的輸出（選擇性）", expanded=False):
            if "image_b64" in prev:
                import base64  # noqa: PLC0415
                img_bytes = base64.b64decode(prev["image_b64"])
                st.image(img_bytes, caption="前一步驟影像", use_container_width=True)

    params = input_mod.render_input()

    btn_label = "▶ 執行"
    if step.optional:
        btn_label += "（可略過）"

    if st.button(btn_label, key=f"run_{step.plugin_id}_{WORKFLOW_ID}", type="primary"):
        if not _auth().check_permission(step.plugin_id, "execute"):
            st.error(f"您沒有執行 {step.plugin_id} 的權限。")
            st.stop()
        try:
            process_mod = PluginLoader.load_module(step.plugin_id, "process")
        except Exception as exc:
            st.error(f"載入 {step.plugin_id} process 失敗：{exc}")
            return

        with st.spinner("運算中…"):
            try:
                result = process_mod.execute_logic(params)
                st.session_state[_wf_key(step.plugin_id)] = result
            except Exception as exc:
                st.error(f"執行失敗：{exc}")
                return

    result = st.session_state.get(_wf_key(step.plugin_id))
    if result is not None:
        st.divider()
        try:
            output_mod = PluginLoader.load_module(step.plugin_id, "output")
            output_mod.render_output(result)
        except Exception as exc:
            st.error(f"載入 {step.plugin_id} output 失敗：{exc}")
            st.json(result)


def main() -> None:
    st.set_page_config(page_title="CIM 工作流程", layout="wide")

    if _LAYER == "output":
        st.info("請在左側頁面操作。")
        st.stop()

    if not WORKFLOW_ID:
        st.error("未設定 CIM_WORKFLOW_ID 環境變數。")
        st.stop()

    try:
        registry = _registry()
        workflow = registry.get_workflow(WORKFLOW_ID)
    except Exception as exc:
        st.error(f"無法載入 Workflow '{WORKFLOW_ID}'：{exc}")
        st.stop()
        return

    st.title(workflow.name)
    if workflow.description:
        st.caption(workflow.description)

    if not workflow.steps:
        st.warning("此工作流程沒有定義任何步驟。")
        return

    tab_labels = [step.tab_label for step in workflow.steps]
    tabs = st.tabs(tab_labels)

    for tab, step in zip(tabs, workflow.steps):
        with tab:
            if step.description:
                st.caption(step.description)
            render_step(step, workflow.steps)


if __name__ == "__main__":
    main()
