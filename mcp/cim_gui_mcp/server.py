"""CIM GUI MCP Server.

Exposes tools so Claude can see and interact with the CIM application UI:
  - sidecar_*  : HTTP calls to the Python sidecar engine
  - browser_*  : Playwright browser automation (Streamlit pages)
  - assert_*   : Pass/fail checks with screenshots

Run with:
    python -m cim_gui_mcp.server
"""
from __future__ import annotations

import json
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent

from .browser_driver import BrowserError, get_driver
from .config import SIDECAR_BASE
from .sidecar_client import SidecarClient, SidecarError, _live_sidecar_base

mcp = FastMCP("cim-gui-mcp")
_client = SidecarClient(base_url=None)  # discovers port dynamically per-call


# ── Sidecar API Tools ─────────────────────────────────────────────────────────


@mcp.tool()
async def sidecar_health() -> str:
    """Check that the CIM Python sidecar is running. Returns 'ok' or an error."""
    try:
        status = await _client.health()
        return f"ok (status={status!r}, base={_client._base})"
    except SidecarError as exc:
        return f"ERROR: {exc}"


@mcp.tool()
async def sidecar_list_tools() -> str:
    """List all available tools from the sidecar. Returns JSON array."""
    try:
        tools = await _client.list_tools()
        return json.dumps(tools, ensure_ascii=False, indent=2)
    except SidecarError as exc:
        return f"ERROR: {exc}"


@mcp.tool()
async def sidecar_start_tool(tool_id: str) -> str:
    """
    Start a tool in the sidecar. Returns JSON with input_url and output_url.

    Args:
        tool_id: The tool ID (e.g. 'cvmod-003', 'workflow-edge-analysis')
    """
    try:
        result = await _client.start_tool(tool_id)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except SidecarError as exc:
        return f"ERROR: {exc}"


@mcp.tool()
async def sidecar_stop_tool() -> str:
    """Stop the currently running tool in the sidecar."""
    try:
        status = await _client.stop_tool()
        return f"stopped (status={status!r})"
    except SidecarError as exc:
        return f"ERROR: {exc}"


# ── Browser Tools ─────────────────────────────────────────────────────────────


@mcp.tool()
async def browser_screenshot(url: str, full_page: bool = False) -> list:
    """
    Take a screenshot of a page and return it as an image Claude can see.

    Args:
        url:       Full URL (e.g. 'http://127.0.0.1:54321')
        full_page: If True, capture the entire scrollable page (default False)
    """
    driver = get_driver()
    try:
        b64 = await driver.screenshot_b64(url, full_page=full_page)
        return [ImageContent(type="image", data=b64, mimeType="image/png")]
    except Exception as exc:
        return [f"ERROR taking screenshot of {url!r}: {exc}"]


@mcp.tool()
async def browser_click(url: str, selector: str, timeout: int = 5000) -> str:
    """
    Click an element on a page.

    Args:
        url:      Full URL of the page
        selector: CSS selector or Playwright text selector (e.g. "text=▶ 執行",
                  "button:has-text('Save')", ".stButton button")
        timeout:  Milliseconds to wait for element (default 5000)
    """
    driver = get_driver()
    try:
        await driver.click(url, selector, timeout=timeout)
        return f"clicked: {selector!r}"
    except BrowserError as exc:
        return f"ERROR: {exc}"


@mcp.tool()
async def browser_fill(url: str, selector: str, value: str, timeout: int = 5000) -> str:
    """
    Fill an input field on a page.

    Args:
        url:      Full URL of the page
        selector: CSS selector for the input element
        value:    Text to type
        timeout:  Milliseconds to wait for element (default 5000)
    """
    driver = get_driver()
    try:
        await driver.fill(url, selector, value, timeout=timeout)
        return f"filled {selector!r} = {value!r}"
    except BrowserError as exc:
        return f"ERROR: {exc}"


@mcp.tool()
async def browser_get_text(url: str, selector: Optional[str] = None) -> str:
    """
    Get the text content of a page or element.

    Args:
        url:      Full URL of the page
        selector: CSS selector (optional; if omitted, returns full page text)
    """
    driver = get_driver()
    try:
        return await driver.get_text(url, selector)
    except BrowserError as exc:
        return f"ERROR: {exc}"


@mcp.tool()
async def browser_wait_for(
    url: str,
    selector: str,
    state: str = "visible",
    timeout: int = 10000,
) -> str:
    """
    Wait for an element to reach a given state before proceeding.

    Args:
        url:      Full URL of the page
        selector: CSS selector to wait for
        state:    'visible' | 'attached' | 'hidden' | 'detached' (default 'visible')
        timeout:  Milliseconds to wait (default 10000)
    """
    driver = get_driver()
    try:
        await driver.wait_for(url, selector, state=state, timeout=timeout)
        return f"ready: {selector!r} is {state!r}"
    except BrowserError as exc:
        return f"ERROR: {exc}"


@mcp.tool()
async def browser_close(url: Optional[str] = None) -> str:
    """
    Close a browser page or all pages.

    Args:
        url: URL of the page to close (optional; if omitted, closes all pages)
    """
    driver = get_driver()
    return await driver.close(url)


# ── Assertion Tools ───────────────────────────────────────────────────────────


@mcp.tool()
async def assert_visible(url: str, selector: str) -> list:
    """
    Assert that an element is visible. Returns pass/fail + screenshot.

    Args:
        url:      Full URL of the page
        selector: CSS selector to check
    """
    driver = get_driver()
    visible = await driver.is_visible(url, selector)
    b64 = await driver.screenshot_b64(url)
    result = {
        "pass": visible,
        "message": f"{'PASS' if visible else 'FAIL'}: {selector!r} is {'visible' if visible else 'NOT visible'}",
    }
    return [
        json.dumps(result),
        ImageContent(type="image", data=b64, mimeType="image/png"),
    ]


@mcp.tool()
async def assert_text(url: str, selector: str, expected: str) -> str:
    """
    Assert that an element's text contains the expected string (case-sensitive substring match).

    Args:
        url:      Full URL of the page
        selector: CSS selector of the element to inspect
        expected: Expected substring in the element's text
    """
    driver = get_driver()
    try:
        actual = await driver.get_text(url, selector)
        passed = expected in actual
        return json.dumps({
            "pass": passed,
            "expected": expected,
            "actual": actual[:500],  # truncate long text
            "message": "PASS" if passed else f"FAIL: {expected!r} not found in text",
        })
    except BrowserError as exc:
        return json.dumps({"pass": False, "message": f"ERROR: {exc}"})


@mcp.tool()
async def assert_no_error(url: str) -> list:
    """
    Assert that no Streamlit error alerts are visible on the page.
    Returns pass/fail + screenshot.

    Args:
        url: Full URL of the page to check
    """
    driver = get_driver()
    errors = await driver.find_errors(url)
    b64 = await driver.screenshot_b64(url)
    result = {
        "pass": len(errors) == 0,
        "errors": errors,
        "message": "PASS: no errors" if not errors else f"FAIL: {len(errors)} error(s) found",
    }
    return [
        json.dumps(result),
        ImageContent(type="image", data=b64, mimeType="image/png"),
    ]


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
