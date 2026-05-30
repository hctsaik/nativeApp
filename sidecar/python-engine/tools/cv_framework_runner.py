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

    from plugin_loader import module_yaml_paths  # noqa: PLC0415

    modules: dict[str, str] = {}
    for yaml_path in module_yaml_paths():  # scripts/ + plugins/*/modules/
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


def _load_plugin_meta(plugin_id: str) -> dict:
    """Read a module's plugin.yaml as a dict (for declarative `form:`/`output:`)."""
    try:
        import yaml  # noqa: PLC0415
        from plugin_loader import find_module_folder  # noqa: PLC0415
        yaml_path = find_module_folder(plugin_id) / "plugin.yaml"
        return yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _load_form_schema(plugin_id: str):
    """The `form:` declarative input schema (or None)."""
    return _load_plugin_meta(plugin_id).get("form")


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
    meta = _load_plugin_meta(module_id)

    # No-code external-GUI tool: a module may declare an `external_gui:` block
    # (launch a desktop program like the Label tool launches X-AnyLabeling) and
    # ship NO input/process code — the framework renders a launch button and
    # handles env sanitization / WDAC workaround / single-instance for it.
    ext_gui = meta.get("external_gui")
    if ext_gui is not None:
        from core.external_gui import render_launcher  # noqa: PLC0415
        st.subheader(selected_name)
        # Launching the external program IS execution — enforce RBAC here too,
        # exactly like the ▶ 執行 path below (otherwise this no-code branch would
        # bypass permissions).
        if not _auth.check_permission(module_id, "execute"):
            st.error("您沒有執行此工具的權限。")
            return
        form_schema = meta.get("form")
        params: dict = {}
        if form_schema:
            from core.forms import render as _render_form  # noqa: PLC0415
            params = _render_form(form_schema, st)

        # When the external program closes, recover its output files and persist
        # a result so the Output page auto-reloads — the full Label-tool loop
        # (launch → work → close → recover), no process code required.
        def _on_result(items: list) -> None:
            # `items` are already parsed when external_gui.collect.parse is set
            # (json→dict, csv→list[dict], lines→list[str]); otherwise file paths.
            # Keep structure intact (don't stringify) but ensure JSON-serializable.
            try:
                json.dumps(items)
                collected = items
            except (TypeError, ValueError):
                collected = [str(it) for it in items]
            payload = {
                "mode": "ready",
                "collected_count": len(items),
                "collected_files": collected,
                "__module_id__": module_id,
                "__module_name__": selected_name,
            }
            try:
                RESULT_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                _post_message("EXECUTE_COMPLETE", {"success": True})
            except Exception:  # noqa: BLE001 - background thread, never crash app
                pass

        render_launcher(ext_gui, params, st, key=module_id, on_result=_on_result)
        return

    process_mod = load_layer(module_id, "process", content_json)

    # No-code input: a module may ship no *_input.py and instead declare its
    # input fields in plugin.yaml `form:` — the framework auto-renders them.
    try:
        input_mod = load_layer(module_id, "input", content_json)
        params = input_mod.render_input()
    except (FileNotFoundError, KeyError):
        schema = meta.get("form")
        if schema is None:
            raise
        from core.forms import render as _render_form  # noqa: PLC0415
        st.subheader(selected_name)
        params = _render_form(schema, st)

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
            # No-code output: a module may ship no *_output.py and instead declare
            # `output:` blocks in plugin.yaml — the framework auto-renders them.
            try:
                output_mod = load_layer(module_id, "output", content_json)
            except (FileNotFoundError, KeyError):
                output_mod = None
            if output_mod is not None:
                if "resolution" in data and isinstance(data["resolution"], list):
                    data["resolution"] = tuple(data["resolution"])
                output_mod.render_output(data)
            else:
                schema = _load_plugin_meta(module_id).get("output")
                if schema is not None:
                    from core.output import render as _render_out  # noqa: PLC0415
                    _render_out(schema, data, st)
                else:
                    st.table({"欄位": list(data.keys()), "值": [str(v) for v in data.values()]})
        except Exception as _exc:
            # Re-raise Streamlit control-flow exceptions (RerunException, StopException)
            # so that st.rerun() / st.stop() inside render_output() work correctly.
            if type(_exc).__module__.startswith("streamlit"):
                raise
            # Fallback: show raw serializable fields as table
            st.table({"欄位": list(data.keys()), "值": [str(v) for v in data.values()]})
    else:
        st.table({"欄位": list(data.keys()), "值": [str(v) for v in data.values()]})



def main() -> None:
    if LAYER == "output":
        run_output()
    else:
        run_input()


if __name__ == "__main__":
    main()
