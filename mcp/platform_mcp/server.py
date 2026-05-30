"""
platform_mcp — CIM 平台層 MCP 服務器

負責平台層操作，讓 Claude 可以：
  - 查看引擎健康狀態
  - 瀏覽可用的工具目錄（modules）
  - 瀏覽 Sheet 工作流定義
  - 管理工具執行（啟動 / 停止）

職責劃分：
  platform_mcp  ← 平台結構查詢與工具管理（此服務器）
  annotation    ← 標注領域操作（datasets, tasks, labels）
  cim-gui       ← GUI 瀏覽器自動化 + 畫面斷言

Run with:
    python -m platform_mcp.server
"""
from __future__ import annotations

import json
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from .config import SIDECAR_BASE

mcp = FastMCP("platform")


# ── Sidecar connection helpers ────────────────────────────────────────────────

def _discover_base() -> str:
    """Try the dev-log port discovery; fall back to config default."""
    import urllib.request
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:19222/dev/status", timeout=2
        ) as resp:
            data = json.loads(resp.read())
            port = int(data.get("sidecarControlPort", 0))
            if port:
                return f"http://127.0.0.1:{port}"
    except Exception:
        pass
    return SIDECAR_BASE


def _get(path: str, timeout: float = 10.0) -> Any:
    base = _discover_base()
    r = httpx.get(f"{base}{path}", timeout=timeout)
    r.raise_for_status()
    return r.json()


def _post(path: str, body: dict | None = None, timeout: float = 10.0) -> Any:
    base = _discover_base()
    r = httpx.post(f"{base}{path}", json=body or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()


# ── Health ────────────────────────────────────────────────────────────────────

@mcp.tool()
def platform_health() -> str:
    """Check that the CIM Python engine is running. Returns status and version."""
    try:
        data = _get("/health")
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as exc:
        return f"ERROR: {exc}"


# ── Tool Catalog ──────────────────────────────────────────────────────────────

@mcp.tool()
def platform_list_tools(enabled_only: bool = True) -> str:
    """
    List all platform tools (modules) registered in the engine.

    enabled_only: if True (default) return only enabled tools.
    Returns a JSON array of {tool_id, name, domain, vendor, version}.
    """
    try:
        tools: list[dict] = _get("/tools")
        if enabled_only:
            tools = [t for t in tools if t.get("enabled", True)]
        summarised = [
            {
                "tool_id": t.get("tool_id"),
                "name":    t.get("name"),
                "domain":  t.get("domain", ""),
                "vendor":  t.get("vendor", ""),
                "version": t.get("version", ""),
            }
            for t in tools
        ]
        return json.dumps(summarised, ensure_ascii=False, indent=2)
    except Exception as exc:
        return f"ERROR: {exc}"


@mcp.tool()
def platform_get_tool(tool_id: str) -> str:
    """Get full metadata for a single tool by its tool_id."""
    try:
        tools: list[dict] = _get("/tools")
        match = next((t for t in tools if t.get("tool_id") == tool_id), None)
        if match is None:
            return json.dumps({"ok": False, "error": f"tool {tool_id!r} not found"})
        return json.dumps(match, ensure_ascii=False, indent=2)
    except Exception as exc:
        return f"ERROR: {exc}"


# ── Sheet / Workflow Catalog ──────────────────────────────────────────────────

@mcp.tool()
def platform_list_sheets() -> str:
    """
    List all workflow sheets (multi-tab tools) registered on this platform.
    Returns a JSON array of {sheet_id, name, description, tab_count}.
    """
    try:
        sheets: list[dict] = _get("/sheets")
        return json.dumps(sheets, ensure_ascii=False, indent=2)
    except Exception as exc:
        return f"ERROR: {exc}"


@mcp.tool()
def platform_get_sheet(sheet_id: str) -> str:
    """Get the tab layout for a specific sheet workflow."""
    try:
        sheets: list[dict] = _get("/sheets")
        match = next((s for s in sheets if s.get("sheet_id") == sheet_id), None)
        if match is None:
            return json.dumps({"ok": False, "error": f"sheet {sheet_id!r} not found"})
        return json.dumps(match, ensure_ascii=False, indent=2)
    except Exception as exc:
        return f"ERROR: {exc}"


# ── Tool Execution ────────────────────────────────────────────────────────────

@mcp.tool()
def platform_start_tool(tool_id: str) -> str:
    """
    Launch a tool by tool_id. Returns {input_url, output_url} for Streamlit tools,
    or the launch result for other tool types.
    """
    try:
        result = _post(f"/tools/{tool_id}/start")
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as exc:
        return f"ERROR: {exc}"


@mcp.tool()
def platform_stop_tool() -> str:
    """Stop the currently running tool."""
    try:
        result = _post("/tools/stop")
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as exc:
        return f"ERROR: {exc}"


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
