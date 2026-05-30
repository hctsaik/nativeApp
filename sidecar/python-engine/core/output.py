"""Declarative output rendering (no-code output layer).

A module can declare how to render its result in `plugin.yaml` under `output:`
instead of hand-writing a Streamlit `render_output()`. Combined with `form:`
(see core.forms), a simple tool needs **no Streamlit code at all** — only a
pure `*_process.py` `execute_logic(params) -> result`.

Schema example (plugin.yaml):

    output:
      - { type: metric,   label: 數量,  key: count }
      - { type: text,     label: 標題,  key: title }
      - { type: list,     key: lines }
      - { type: table,    key: rows }          # list[dict] | list[list]
      - { type: json,     key: data }
      - { type: image,    key: image_path }    # filesystem path or data-URI/base64
      - { type: markdown, value: "## 固定文字" }

Each block reads `result[key]` (or a literal `value`). The pure parts
(validation/normalization) are Streamlit-free and unit-tested; `render()` is a
thin adapter over the `st` module. See tests/test_output.py.
"""

from __future__ import annotations

from typing import Any

SUPPORTED_TYPES = {"metric", "text", "list", "table", "json", "image", "markdown", "caption"}


class OutputSchemaError(ValueError):
    """Raised when an `output:` schema is malformed."""


def normalize_block(block: dict, index: int = 0) -> dict:
    if not isinstance(block, dict):
        raise OutputSchemaError(f"output[{index}] 必須是物件（dict）")
    btype = block.get("type")
    if btype not in SUPPORTED_TYPES:
        raise OutputSchemaError(
            f"output[{index}] 的 type '{btype}' 不支援；可用：{sorted(SUPPORTED_TYPES)}"
        )
    if "key" not in block and "value" not in block:
        raise OutputSchemaError(f"output[{index}]（{btype}）需要 'key'（讀 result）或 'value'（固定值）")
    return {
        "type": btype,
        "key": block.get("key"),
        "value": block.get("value"),
        "label": block.get("label"),
    }


def normalize_schema(schema: Any) -> list[dict]:
    if schema is None:
        return []
    if not isinstance(schema, list):
        raise OutputSchemaError(f"output: 必須是區塊清單（list），得到 {type(schema).__name__}")
    return [normalize_block(b, i) for i, b in enumerate(schema)]


def _resolve(block: dict, result: dict) -> Any:
    if block.get("value") is not None:
        return block["value"]
    return result.get(block.get("key"))


def render(schema: Any, result: dict, st: Any) -> None:
    """Render a declarative output schema with Streamlit. `st` is injected so the
    pure logic stays testable."""
    blocks = normalize_schema(schema)
    for block in blocks:
        t = block["type"]
        val = _resolve(block, result)
        label = block.get("label") or block.get("key") or ""
        if t == "metric":
            st.metric(label, val)
        elif t == "text":
            if label:
                st.write(f"**{label}**：{val}")
            else:
                st.write(val)
        elif t == "caption":
            st.caption(val if not label else f"{label}：{val}")
        elif t == "markdown":
            st.markdown(val)
        elif t == "list":
            for item in (val or []):
                st.write(item)
        elif t == "table":
            if val:
                st.table(val)
            else:
                st.caption(f"（{label or 'table'} 無資料）")
        elif t == "json":
            st.json(val if val is not None else {})
        elif t == "image":
            if val:
                st.image(val)
            else:
                st.caption(f"（{label or 'image'} 無影像）")
