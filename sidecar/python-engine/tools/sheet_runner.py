from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

_ENGINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ENGINE_DIR))

from auth_provider import AuthProvider  # noqa: E402
from plugin_loader import PluginLoader  # noqa: E402
from plugin_registry import PluginRegistry  # noqa: E402

LOG_DIR   = Path(os.environ.get("CIM_LOG_DIR", "/tmp"))
SHEET_ID  = os.environ.get("CIM_SHEET_ID", "")
PLUGIN_ID = os.environ.get("CIM_PLUGIN_ID", "")
_LAYER    = os.environ.get("CIM_TOOL_LAYER", "input")
_DB_PATH  = Path(os.environ.get("CIM_TOOLS_DB", str(LOG_DIR / "data" / "tools.sqlite")))


def _result_file() -> Path:
    return LOG_DIR / f"sheet_{SHEET_ID}_{PLUGIN_ID}_result.json"


def _registry() -> PluginRegistry:
    return PluginRegistry(db_path=_DB_PATH, scripts_dir=_ENGINE_DIR / "scripts")


def _auth() -> AuthProvider:
    return AuthProvider(db_path=_DB_PATH)


def _post_message(msg_type: str, payload: dict) -> None:
    payload_json = json.dumps({"type": msg_type, "source": "cim-platform", "payload": payload, "_cim": True})
    components.html(
        f"""<script>window.top.postMessage({payload_json}, '*');</script>""",
        height=0,
    )


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


# ── Input 層 ───────────────────────────────────────────────────────────────────

def run_input() -> None:
    _hide_streamlit_chrome()

    if not SHEET_ID or not PLUGIN_ID:
        st.error("Missing CIM_SHEET_ID or CIM_PLUGIN_ID environment variable.")
        st.stop()

    try:
        registry = _registry()
        sheet = registry.get_sheet(SHEET_ID)
    except Exception as exc:
        st.error(f"無法載入 Sheet '{SHEET_ID}'：{exc}")
        st.stop()
        return

    # Sheet 標題（顯示在頂部，提供上下文）
    if sheet.description:
        st.caption(sheet.description)

    content_json: dict | None = None
    if not PluginLoader.is_dev_mode():
        try:
            content_json = registry.get_plugin_content(PLUGIN_ID)
        except KeyError:
            st.error(
                f"**{PLUGIN_ID}** 尚未發布至 Prod——"
                "請至管理中心執行「一鍵發布到 Prod」後再試。"
            )
            return
        except Exception as exc:
            st.error(f"載入 {PLUGIN_ID} Prod 版本失敗：{exc}")
            return

    try:
        input_mod = PluginLoader.load_module(PLUGIN_ID, "input", content_json)
    except Exception as exc:
        st.error(f"載入 {PLUGIN_ID} input 失敗：{exc}")
        return

    params = input_mod.render_input()

    if st.button("▶ 執行", key=f"run_{PLUGIN_ID}_{SHEET_ID}", type="primary"):
        if not _auth().check_permission(PLUGIN_ID, "execute"):
            st.error(f"您沒有執行 {PLUGIN_ID} 的權限。")
            return
        try:
            process_mod = PluginLoader.load_module(PLUGIN_ID, "process", content_json)
        except Exception as exc:
            st.error(f"載入 {PLUGIN_ID} process 失敗：{exc}")
            return

        _post_message("EXECUTE_START", {})
        with st.spinner("運算中…"):
            try:
                result = process_mod.execute_logic(params)

                serializable = {
                    k: (list(v) if isinstance(v, tuple) else v)
                    for k, v in result.items()
                    if isinstance(v, (str, int, float, bool, list, tuple, dict, type(None)))
                }
                _result_file().write_text(
                    json.dumps(serializable, ensure_ascii=False), encoding="utf-8"
                )
                _post_message("EXECUTE_COMPLETE", {"success": True, "plugin_id": PLUGIN_ID})
                st.success("執行完成，請切換至 Output 頁籤查看結果。")

            except Exception as exc:
                _post_message("EXECUTE_COMPLETE", {"success": False, "error": str(exc)})
                st.error(f"執行失敗：{exc}")


# ── Output 層 ──────────────────────────────────────────────────────────────────

def run_output() -> None:
    _hide_streamlit_chrome()

    if not SHEET_ID or not PLUGIN_ID:
        st.info("尚未執行，請在左側 Input 頁籤按下 ▶ 執行。")
        time.sleep(1)
        st.rerun()
        return

    rfile = _result_file()
    result: dict = {}
    if rfile.exists():
        current_mtime = rfile.stat().st_mtime
        last_mtime = st.session_state.get("_sheet_result_mtime")
        if last_mtime != current_mtime:
            st.session_state["_sheet_result_mtime"] = current_mtime
            st.rerun()
            return
        try:
            result = json.loads(rfile.read_text(encoding="utf-8"))
        except Exception as exc:
            st.error(f"讀取結果失敗：{exc}")
            time.sleep(2)
            st.rerun()
            return

    try:
        registry = _registry()
        content_json = None
        if not PluginLoader.is_dev_mode():
            try:
                content_json = registry.get_plugin_content(PLUGIN_ID)
            except Exception:
                pass
        output_mod = PluginLoader.load_module(PLUGIN_ID, "output", content_json)
        output_mod.render_output(result)
    except Exception as exc:
        # Re-raise Streamlit control-flow exceptions (RerunException, StopException)
        # so that st.rerun() / st.stop() inside render_output() work correctly.
        if type(exc).__module__.startswith("streamlit"):
            raise
        st.error(f"載入 {PLUGIN_ID} output 失敗：{exc}")
        st.json(result)


# ── 進入點 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(page_title="CIM 頁面", layout="wide")

    if _LAYER == "output":
        run_output()
    else:
        run_input()


if __name__ == "__main__":
    main()
