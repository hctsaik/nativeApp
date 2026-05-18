from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_result(result_file: Path, user_input: dict[str, Any], process_result: dict[str, Any]) -> None:
    """Write the standard result envelope to disk.

    Every tool result is wrapped as:
        { "user_input": {...}, "process_result": {...} }

    Input pages call this with the fields the user filled in plus whatever the
    process computed.  Output pages read both sections from the same file so
    they always know both the input context and the computed outcome.
    """
    envelope = {"user_input": user_input, "process_result": process_result}
    result_file.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")


def read_result(result_file: Path) -> dict[str, Any] | None:
    """Read the result envelope written by write_result.

    Returns a dict with keys ``user_input`` and ``process_result``, or None if
    the file does not exist or is malformed.
    """
    try:
        data = json.loads(result_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if "user_input" not in data or "process_result" not in data:
        return None
    return data
