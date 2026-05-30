"""Process layer for the declarative-form demo (module_007).

Pure business logic — no Streamlit. `params` comes from the plugin.yaml `form:`
schema, auto-rendered by the framework (no *_input.py needed).
"""

from __future__ import annotations


def execute_logic(params: dict) -> dict:
    title = str(params.get("title", ""))
    count = int(params.get("count", 1) or 1)
    mode = params.get("mode", "原樣")
    if mode == "大寫":
        title = title.upper()
    elif mode == "小寫":
        title = title.lower()
    if params.get("shout"):
        title = f"{title}!"
    lines = [f"{i + 1}. {title}" for i in range(count)]
    return {"mode": "ready", "title": title, "count": count, "lines": lines}
