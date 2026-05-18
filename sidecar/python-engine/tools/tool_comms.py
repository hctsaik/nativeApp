from __future__ import annotations

"""Helpers for communicating between a Streamlit tool page and the CIM Portal.

The Portal (Electron / React) hosts tool pages inside iframes.  Both sides
speak a postMessage protocol defined in @cim/shared-protocol.  These helpers
let an Input page signal the Portal without repeating the same boilerplate.

Typical usage in an Input page
--------------------------------
    from tool_comms import notify_start, notify_complete

    if st.button("▶ 執行"):
        notify_start()
        try:
            ...compute...
            write_result(RESULT_FILE, user_input, process_result)
            notify_complete()
        except Exception as exc:
            notify_complete(success=False, error=str(exc))
            st.error(f"執行失敗：{exc}")
"""

import json

import streamlit.components.v1 as components


def _post(msg_type: str, payload: dict) -> None:
    blob = json.dumps({"type": msg_type, "payload": payload, "_cim": True})
    # window.top reaches the Portal regardless of iframe nesting depth.
    # (window.parent would stop at the Streamlit page, one level too short.)
    components.html(
        f"<script>window.top.postMessage({blob}, '*');</script>",
        height=0,
    )


def notify_start() -> None:
    """Tell the Portal that processing has begun (shows loading overlay)."""
    _post("EXECUTE_START", {})


def notify_complete(success: bool = True, error: str = "") -> None:
    """Tell the Portal that processing finished.

    On success the Portal will:
      - hide the loading overlay
      - switch to the Output tab
      - reload the output iframe so it picks up the new result file

    On failure the Portal hides the overlay but stays on the Input tab.
    """
    payload: dict = {"success": success}
    if error:
        payload["error"] = error
    _post("EXECUTE_COMPLETE", payload)
