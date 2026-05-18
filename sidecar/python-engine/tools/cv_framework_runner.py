from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from auth_provider import AuthProvider  # noqa: E402
from plugin_loader import PluginLoader  # noqa: E402
from plugin_registry import PluginRegistry  # noqa: E402

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
LAYER = os.environ.get("CIM_TOOL_LAYER", "input")  # "input" or "output"
TOOL_ID = os.environ.get("CIM_TOOL_ID", "cv-framework")
MODULE_ID = os.environ.get("CIM_MODULE_ID", "")     # set → skip module selector
LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", "/tmp"))
RESULT_FILE = LOG_DIR / f"{TOOL_ID}_result.json"
_DB_PATH = Path(os.environ.get("CIM_TOOLS_DB", str(LOG_DIR / "data" / "tools.sqlite")))
_auth = AuthProvider(db_path=_DB_PATH)


def _get_content_json(plugin_id: str) -> dict | None:
    """In PROD mode, load published content from DB. Returns None in DEV mode."""
    if PluginLoader.is_dev_mode():
        return None
    try:
        reg = PluginRegistry(db_path=_DB_PATH, scripts_dir=SCRIPTS_DIR)
        return reg.get_plugin_content(plugin_id)
    except KeyError:
        return {}  # sentinel: published record not found


def discover_modules() -> dict[str, str]:
    """Scan scripts/*/plugin.yaml for cv_framework modules; return {display_name: plugin_id}.

    plugin.yaml is the source of truth. Folders without plugin.yaml are ignored.
    Only modules with runner: cv_framework (or no runner field) and enabled: true are included.
    """
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        return {}

    modules: dict[str, str] = {}
    for yaml_path in sorted(SCRIPTS_DIR.glob("*/plugin.yaml")):
        folder = yaml_path.parent
        if not folder.is_dir():
            continue
        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue

        runner = data.get("runner", "cv_framework")
        if runner != "cv_framework":
            continue
        if not data.get("enabled", True):
            continue

        plugin_id = data.get("id") or folder.name
        name = data.get("name", plugin_id)
        modules[name] = plugin_id
    return modules


def load_layer(plugin_id: str, layer: str, content_json: dict | None = None):
    if not PluginLoader.is_dev_mode():
        if content_json is None:
            content_json = _get_content_json(plugin_id)
        if content_json == {}:  # sentinel from KeyError
            st.error(
                f"### ⚠️ 模組尚未發布至 PROD\n\n"
                f"`{plugin_id}` 在 PROD 模式下需要先發布才能執行。\n\n"
                f"**操作步驟：**\n"
                f"1. 關閉此工具，切換至 **DEV 模式**（`start-dev.bat`）\n"
                f"2. 啟動「管理中心」\n"
                f"3. 工具管理 → `{plugin_id}` → **🚀 一鍵發布到 Prod**\n"
                f"4. 重新以 **PROD 模式**（`start-prod.bat`）啟動"
            )
            st.stop()
    return PluginLoader.load_module(plugin_id, layer, content_json)


def _hide_streamlit_chrome() -> None:
    st.markdown(
        """
        <style>
        header[data-testid="stHeader"] { display: none !important; height: 0 !important; }
        #MainMenu { display: none !important; }
        footer { display: none !important; }
        [data-testid="stToolbar"] { display: none !important; }
        [data-testid="stDecoration"] { display: none !important; }
        [data-testid="stStatusWidget"] { display: none !important; }
        .block-container,
        [data-testid="stMainBlockContainer"] {
            padding-top: 0.5rem !important;
            padding-bottom: 1rem !important;
            max-width: 100% !important;
        }
        section[data-testid="stMain"] { padding-top: 0 !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _post_message(msg_type: str, payload: dict) -> None:
    """Send a postMessage to the Portal host via an invisible iframe script."""
    payload_json = json.dumps({"type": msg_type, "payload": payload, "_cim": True})
    components.html(
        f"""<script>window.top.postMessage({payload_json}, '*');</script>""",
        height=0,
    )


def run_input() -> None:
    st.set_page_config(page_title="CIM CV 框架 — Input", layout="wide")
    _hide_streamlit_chrome()

    modules = discover_modules()
    if not modules:
        st.error("未找到任何模組。")
        st.stop()

    # CIM_MODULE_ID may be short ("003") or full ("module_003"); normalise to plugin_id
    _mid_normalised = MODULE_ID
    if MODULE_ID and MODULE_ID not in modules.values():
        _mid_normalised = f"module_{MODULE_ID}"

    if _mid_normalised and _mid_normalised in modules.values():
        module_id = _mid_normalised
        selected_name = next(k for k, v in modules.items() if v == module_id)
    else:
        with st.sidebar:
            selected_name = st.selectbox("選擇模組", list(modules.keys()))
        module_id = modules[selected_name]
    content_json = _get_content_json(module_id) if not PluginLoader.is_dev_mode() else None
    input_mod = load_layer(module_id, "input", content_json)
    process_mod = load_layer(module_id, "process", content_json)

    params = input_mod.render_input()

    if st.button("▶ 執行", type="primary"):
        _post_message("EXECUTE_START", {})
        if not _auth.check_permission(module_id, "execute"):
            st.error("您沒有執行此模組的權限。")
            st.stop()
        with st.spinner("運算中…"):
            try:
                result = process_mod.execute_logic(params)
                # Persist result for output Streamlit to read
                serializable = {
                    k: (list(v) if isinstance(v, tuple) else v)
                    for k, v in result.items()
                    if isinstance(v, (str, int, float, bool, list, tuple, dict, type(None)))
                }
                serializable["__module_id__"] = module_id
                serializable["__module_name__"] = selected_name
                RESULT_FILE.write_text(json.dumps(serializable, ensure_ascii=False), encoding="utf-8")
                _post_message("EXECUTE_COMPLETE", {"success": True})
                st.success("執行完成，請切換至 Output 頁籤查看結果。")
            except Exception as exc:
                _post_message("EXECUTE_COMPLETE", {"success": False, "error": str(exc)})
                st.error(f"執行失敗：{exc}")


def run_output() -> None:
    st.set_page_config(page_title="CIM CV 框架 — Output", layout="wide")
    _hide_streamlit_chrome()
    st.title("執行結果")

    # Auto-refresh until result file appears, and re-check when it updates
    if not RESULT_FILE.exists():
        st.info("尚未執行，請在 Input 頁籤完成輸入並按下 ▶ 執行。")
        time.sleep(1)
        st.rerun()
        return

    current_mtime = RESULT_FILE.stat().st_mtime
    last_mtime = st.session_state.get("_result_mtime")
    if last_mtime != current_mtime:
        st.session_state["_result_mtime"] = current_mtime
        st.rerun()
        return

    try:
        data = json.loads(RESULT_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        st.error(f"讀取結果失敗：{exc}")
        time.sleep(2)
        st.rerun()
        return

    module_id = data.pop("__module_id__", None)
    module_name = data.pop("__module_name__", "Unknown")
    st.caption(f"模組：{module_name}")

    if module_id:
        try:
            content_json = _get_content_json(module_id) if not PluginLoader.is_dev_mode() else None
            output_mod = load_layer(module_id, "output", content_json)
            if "resolution" in data and isinstance(data["resolution"], list):
                data["resolution"] = tuple(data["resolution"])
            output_mod.render_output(data)
        except Exception:
            # Fallback: show raw serializable fields as table
            st.table({"欄位": list(data.keys()), "值": [str(v) for v in data.values()]})
    else:
        st.table({"欄位": list(data.keys()), "值": [str(v) for v in data.values()]})

    # Poll for result file updates every 3 seconds
    time.sleep(3)
    st.rerun()


def main() -> None:
    if LAYER == "output":
        run_output()
    else:
        run_input()


if __name__ == "__main__":
    main()
