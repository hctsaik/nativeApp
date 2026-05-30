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
    deco = params.get("deco") or []
    indent = " " * int(params.get("indent", 0) or 0)
    lines = []
    for i in range(count):
        prefix = ""
        if "編號" in deco:
            prefix += f"{i + 1}. "
        if "破折號" in deco:
            prefix += "- "
        if "星號" in deco:
            prefix += "★ "
        lines.append(f"{indent}{prefix}{title}")
    return {"mode": "ready", "title": title, "count": count, "lines": lines}
