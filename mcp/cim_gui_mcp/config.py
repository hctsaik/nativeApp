from __future__ import annotations

import json
import os
import urllib.request


def _discover_sidecar_port(fallback: int = 8765) -> int:
    """Query the dev-log server for the live sidecar control port."""
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:19222/dev/status", timeout=2
        ) as resp:
            data = json.loads(resp.read())
            port = int(data["sidecarControlPort"])
            return port if port else fallback
    except Exception:
        return fallback


_env_port = os.environ.get("CIM_SIDECAR_PORT", "")
_discover = os.environ.get("CIM_MCP_DISCOVER_SIDECAR", "0") == "1"
SIDECAR_PORT: int = (
    int(_env_port)
    if _env_port
    else _discover_sidecar_port() if _discover else 8765
)
SIDECAR_BASE: str = f"http://127.0.0.1:{SIDECAR_PORT}"

# Set CIM_MCP_HEADLESS=0 to watch Claude operate the browser (debug mode)
BROWSER_HEADLESS: bool = os.environ.get("CIM_MCP_HEADLESS", "1") == "1"

# Default timeout for browser operations in milliseconds
DEFAULT_TIMEOUT: int = int(os.environ.get("CIM_MCP_TIMEOUT", "10000"))
