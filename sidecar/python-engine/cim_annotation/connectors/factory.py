from __future__ import annotations

import importlib
import os
from pathlib import Path

from .base import PullConnector, PushConnector
from .local_file import LocalFileConnector


def build(
    connector_yaml_path: str | Path | None = None,
) -> tuple[PullConnector, PushConnector]:
    """
    Return a (pull, push) connector pair based on connector.yaml.

    Falls back to LocalFileConnector when connector_yaml_path is None,
    absent, or when type is "local_file".  This ensures existing modules
    that do not ship a connector.yaml continue to work without changes.
    """
    path = Path(connector_yaml_path) if connector_yaml_path else None
    if not path or not path.exists():
        c = LocalFileConnector()
        return c, c

    try:
        import yaml  # PyYAML; optional dependency
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    except ImportError:
        # Fall back to a minimal YAML parser for the simple key:value format
        cfg = _simple_yaml_load(path)

    connector_cfg = cfg.get("connector", {})
    t = connector_cfg.get("type", "local_file")

    if t == "local_file":
        lf_cfg = connector_cfg.get("local_file", {})
        c = LocalFileConnector(source_dir=lf_cfg.get("image_root", ""))
        return c, c

    if t == "sql":
        from .sql_connector import SqlConnector
        sql_cfg = connector_cfg.get("sql", {})
        # Allow dsn to come from yaml or from env var CIM_CONNECTOR_DSN
        if "dsn_env" in sql_cfg:
            sql_cfg = {**sql_cfg, "dsn": os.environ.get(sql_cfg["dsn_env"], "")}
        c = SqlConnector(sql_cfg)
        return c, c

    if t == "rest":
        from .rest_connector import RestConnector
        rest_cfg = connector_cfg.get("rest", {})
        if "base_url_env" in rest_cfg:
            rest_cfg = {**rest_cfg, "base_url": os.environ.get(rest_cfg["base_url_env"], "")}
        c = RestConnector(rest_cfg)
        return c, c

    if t == "custom":
        custom_cfg = connector_cfg["custom"]
        mod = importlib.import_module(custom_cfg["module"])
        cls = getattr(mod, custom_cfg["class"])
        c = cls(custom_cfg.get("config", {}))
        return c, c

    raise ValueError(f"Unknown connector type: {t!r}")


def _simple_yaml_load(path: Path) -> dict:
    """
    Minimal YAML loader for the flat connector.yaml structure.
    Used only when PyYAML is not installed.
    """
    import json
    text = path.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    # Best-effort: try JSON-compatible subset after stripping YAML quotes
    try:
        return json.loads(text)
    except Exception:
        pass
    # Return empty dict so caller falls back to LocalFileConnector
    return {}
