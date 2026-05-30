"""Declarative input forms (no-code input layer).

A module can declare its input fields in `plugin.yaml` under `form:` instead of
hand-writing a Streamlit `render_input()`. The framework auto-renders the form
when a module ships no `*_input.py` (see tools/cv_framework_runner.run_input),
so simple "fill a few fields → run" tools need **no Python input code**.

Schema example (plugin.yaml):

    form:
      - { key: threshold, type: number, label: 閾值, default: 0.5, min: 0, max: 1, step: 0.05 }
      - { key: mode,      type: select, label: 模式, options: [fast, accurate], default: fast }
      - { key: name,      type: text,   label: 名稱, default: "", placeholder: 請輸入 }
      - { key: enabled,   type: checkbox, label: 啟用, default: true }
      - { key: notes,     type: textarea, label: 備註 }
      - { key: image,     type: file,   label: 影像, accept: [png, jpg, jpeg] }

The pure parts (validation, normalization, widget-call planning, value coercion)
are Streamlit-free and unit-tested; `render()` is a thin adapter over the `st`
module. See tests/test_forms.py and docs/platform/shared-components.md.
"""

from __future__ import annotations

from typing import Any

SUPPORTED_TYPES = {
    "text", "textarea", "number", "integer",
    "select", "multiselect", "checkbox", "slider", "file",
    "date", "time",
}


class FormSchemaError(ValueError):
    """Raised when a `form:` schema is malformed (surfaced to the author)."""


def normalize_field(field: dict, index: int = 0) -> dict:
    """Validate one field and fill defaults. Pure (no Streamlit). Raises
    FormSchemaError with an author-friendly message on a bad spec."""
    if not isinstance(field, dict):
        raise FormSchemaError(f"form[{index}] 必須是物件（dict），得到 {type(field).__name__}")
    key = field.get("key")
    if not key or not isinstance(key, str):
        raise FormSchemaError(f"form[{index}] 缺少有效的 'key'（欄位名稱）")
    ftype = field.get("type", "text")
    if ftype not in SUPPORTED_TYPES:
        raise FormSchemaError(
            f"form 欄位 '{key}' 的 type '{ftype}' 不支援；可用：{sorted(SUPPORTED_TYPES)}"
        )
    out: dict[str, Any] = {
        "key": key,
        "type": ftype,
        "label": field.get("label", key),
        "help": field.get("help"),
        "default": field.get("default"),
    }
    if ftype in ("select", "multiselect"):
        options = field.get("options")
        if not isinstance(options, list) or not options:
            raise FormSchemaError(f"form 欄位 '{key}'（{ftype}）需要非空的 'options' 清單")
        out["options"] = options
    if ftype in ("number", "integer", "slider"):
        out["min"] = field.get("min")
        out["max"] = field.get("max")
        out["step"] = field.get("step")
    if ftype == "slider" and (out["min"] is None or out["max"] is None):
        raise FormSchemaError(f"form 欄位 '{key}'（slider）需要 'min' 與 'max'")
    if ftype == "text":
        out["placeholder"] = field.get("placeholder")
    if ftype == "file":
        out["accept"] = field.get("accept")  # list[str] of extensions, optional
    return out


def normalize_schema(schema: Any) -> list[dict]:
    """Validate a whole `form:` schema → list of normalized fields. Pure."""
    if schema is None:
        return []
    if not isinstance(schema, list):
        raise FormSchemaError(f"form: 必須是欄位清單（list），得到 {type(schema).__name__}")
    keys: set[str] = set()
    norm: list[dict] = []
    for i, f in enumerate(schema):
        nf = normalize_field(f, i)
        if nf["key"] in keys:
            raise FormSchemaError(f"form 欄位 'key' 重複：{nf['key']}")
        keys.add(nf["key"])
        norm.append(nf)
    return norm


def widget_call(field: dict) -> tuple[str, dict]:
    """Plan the Streamlit widget call for a normalized field, as
    (st_method_name, kwargs). Pure — lets us unit-test rendering intent
    without a live Streamlit runtime."""
    t = field["type"]
    common = {"label": field["label"]}
    if field.get("help"):
        common["help"] = field["help"]
    if t == "text":
        return "text_input", {**common, "value": field.get("default") or "",
                              "placeholder": field.get("placeholder") or ""}
    if t == "textarea":
        return "text_area", {**common, "value": field.get("default") or ""}
    if t == "checkbox":
        return "checkbox", {**common, "value": bool(field.get("default"))}
    if t in ("number", "integer"):
        kw = {**common, "value": field.get("default")
              if field.get("default") is not None else (0 if t == "integer" else 0.0)}
        for k in ("min", "max", "step"):
            if field.get(k) is not None:
                kw[{"min": "min_value", "max": "max_value", "step": "step"}[k]] = field[k]
        return "number_input", kw
    if t == "slider":
        return "slider", {**common, "min_value": field["min"], "max_value": field["max"],
                          "value": field.get("default") if field.get("default") is not None else field["min"],
                          **({"step": field["step"]} if field.get("step") is not None else {})}
    if t == "select":
        opts = field["options"]
        idx = opts.index(field["default"]) if field.get("default") in opts else 0
        return "selectbox", {**common, "options": opts, "index": idx}
    if t == "multiselect":
        return "multiselect", {**common, "options": field["options"],
                               "default": field.get("default") or []}
    if t == "file":
        kw = {**common}
        if field.get("accept"):
            kw["type"] = field["accept"]
        return "file_uploader", kw
    if t == "date":
        kw = {**common}
        if field.get("default") is not None:
            kw["value"] = field["default"]
        return "date_input", kw
    if t == "time":
        kw = {**common}
        if field.get("default") is not None:
            kw["value"] = field["default"]
        return "time_input", kw
    raise FormSchemaError(f"無法對應 widget：type={t}")  # pragma: no cover


def coerce(field: dict, value: Any) -> Any:
    """Coerce a widget's returned value into the param value execute_logic sees."""
    if field["type"] == "integer" and value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    # date/time widgets return datetime.date/time → ISO strings so the value is
    # JSON-serializable and predictable for execute_logic / output.
    if field["type"] in ("date", "time") and value is not None and hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def render(schema: Any, st: Any) -> dict:
    """Render a declarative form with Streamlit and return {key: value}.

    `st` is injected (the streamlit module) so the pure logic above stays
    testable. Returns the params dict for execute_logic(params).
    """
    fields = normalize_schema(schema)
    values: dict[str, Any] = {}
    for field in fields:
        method, kwargs = widget_call(field)
        widget = getattr(st, method)
        values[field["key"]] = coerce(field, widget(**kwargs))
    return values
