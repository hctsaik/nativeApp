"""Synchronous facade over the **cim-gui MCP** machinery, for the LV BDD suite.

The project's E2E story is the ``cim-gui`` MCP server (``mcp/cim_gui_mcp``): its
``sidecar_*`` tools call ``SidecarClient`` (HTTP to the engine) and its
``browser_*`` / ``assert_*`` tools call ``BrowserDriver`` (Playwright on the live
Streamlit page). This driver imports and drives **those exact callables**, so a
scenario step here exercises the same engine-layer code an MCP tool call would —
identical HTTP requests and the same Playwright session. (We also expose
``prove_mcp_server`` which launches the real ``python -m cim_gui_mcp.server`` over
stdio and lists its tools, to demonstrate the literal MCP server boots.)

Why a sync facade: scenarios read top-to-bottom; the underlying MCP code is
async, so we run it on one private event loop.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[5]          # c:\code\claude\nativeApp
_MCP_PKG = _REPO / "mcp"                              # c:\code\claude\nativeApp\mcp
if str(_MCP_PKG) not in sys.path:
    sys.path.insert(0, str(_MCP_PKG))

# headless by default for CI/this environment
os.environ.setdefault("CIM_MCP_HEADLESS", "1")

from cim_gui_mcp.browser_driver import BrowserDriver, BrowserError  # noqa: E402
from cim_gui_mcp.sidecar_client import SidecarClient, SidecarError  # noqa: E402

__all__ = ["MCPDriver", "BrowserError", "SidecarError", "prove_mcp_server"]


class MCPDriver:
    """Sync wrapper around cim-gui's SidecarClient + BrowserDriver."""

    def __init__(self, base_url: str, headless: bool = True,
                 default_timeout_ms: int = 90_000) -> None:
        self.base_url = base_url.rstrip("/")
        self._loop = asyncio.new_event_loop()
        # explicit base so we hit the engine we booted, not the dev-log discovery
        self._client = SidecarClient(base_url=self.base_url, timeout=120.0)
        self._browser = BrowserDriver(headless=headless,
                                      default_timeout=default_timeout_ms)

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    # ── sidecar_* (engine HTTP) ──────────────────────────────────────────────
    def health(self) -> str:
        return self._run(self._client.health())

    def list_tools(self) -> list[dict]:
        return self._run(self._client.list_tools())

    def start_tool(self, tool_id: str) -> dict:
        return self._run(self._client.start_tool(tool_id))

    def stop_tool(self) -> str:
        try:
            return self._run(self._client.stop_tool())
        except SidecarError:
            return "n/a"

    # ── browser_* / assert_* (Playwright on live Streamlit) ──────────────────
    def screenshot(self, url: str, out_path: str | Path, full_page: bool = True) -> Path:
        raw = self._run(self._browser.screenshot(url, full_page=full_page))
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
        return p

    def get_text(self, url: str, selector: str | None = None) -> str:
        return self._run(self._browser.get_text(url, selector))

    def fill(self, url: str, selector: str, value: str, timeout: int | None = None) -> None:
        self._run(self._browser.fill(url, selector, value, timeout=timeout))

    def click(self, url: str, selector: str, timeout: int | None = None) -> None:
        self._run(self._browser.click(url, selector, timeout=timeout))

    def wait_for(self, url: str, selector: str, state: str = "visible",
                 timeout: int | None = None) -> None:
        self._run(self._browser.wait_for(url, selector, state=state, timeout=timeout))

    def is_visible(self, url: str, selector: str) -> bool:
        return self._run(self._browser.is_visible(url, selector))

    def find_errors(self, url: str) -> list[str]:
        return self._run(self._browser.find_errors(url))

    # ── higher-level helpers ─────────────────────────────────────────────────
    def wait_render(self, url: str, min_chars: int = 40, timeout_s: int = 90) -> str:
        """Wait until the Streamlit script body has actually rendered (its
        per-session websocket has run app.py), not just the SPA shell."""
        import time
        # force the page to load (BrowserDriver.get_page caches per-url)
        self.get_text(url)  # triggers goto
        deadline = time.time() + timeout_s
        txt = ""
        while time.time() < deadline:
            txt = self.get_text(url)
            if len(txt.strip()) >= min_chars:
                return txt
            time.sleep(1.0)
        return txt

    def wait_text(self, url: str, needle: str, timeout_s: int = 60) -> bool:
        import time
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if needle in self.get_text(url):
                return True
            time.sleep(1.0)
        return False

    def assert_text(self, url: str, needle: str) -> tuple[bool, str]:
        body = self.get_text(url)
        return (needle in body), body

    def assert_no_traceback(self, url: str) -> tuple[bool, list[str]]:
        body = self.get_text(url)
        bad = [m for m in ("Traceback (most recent call last)", "RuntimeError",
                           "did not become ready") if m in body]
        return (not bad), bad

    def count(self, url: str, selector: str) -> int:
        async def _c():
            page = await self._browser.get_page(url)
            return await page.locator(selector).count()
        return self._run(_c())

    def click_by_text(self, url: str, text: str, exact: bool = False,
                      timeout: int | None = None) -> None:
        """Click a button by its (visible) accessible name — robust to Streamlit's
        emoji/whitespace button labels."""
        async def _click():
            page = await self._browser.get_page(url)
            loc = page.get_by_role("button", name=text, exact=exact)
            await loc.first.click(timeout=timeout or self._browser._default_timeout)
        self._run(_click())

    def close(self) -> None:
        try:
            self._run(self._browser.close())
        finally:
            self._loop.close()


def prove_mcp_server(timeout_s: float = 30.0) -> dict:
    """Launch the real ``python -m cim_gui_mcp.server`` and list its tools over
    the MCP stdio protocol — proof the literal MCP server (not just its driver
    modules) boots and advertises the browser_/assert_/sidecar_ tools.

    Returns {"ok": bool, "tools": [...], "error": str|None}. Best-effort: if the
    ``mcp`` client SDK is unavailable it reports ok=False without raising.
    """
    import asyncio as _asyncio

    async def _list() -> list[str]:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "cim_gui_mcp.server"],
            cwd=str(_MCP_PKG),
            env={**os.environ, "PYTHONPATH": str(_MCP_PKG), "CIM_MCP_HEADLESS": "1"},
        )
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                resp = await session.list_tools()
                return [t.name for t in resp.tools]

    try:
        tools = _asyncio.run(_list())
        return {"ok": True, "tools": tools, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "tools": [], "error": f"{type(exc).__name__}: {exc}"}


def mcp_stdio_smoke(base_url: str, tool_id: str, expect_text: str,
                    shot_path: str | Path | None = None,
                    timeout_s: float = 180.0) -> dict:
    """Drive one tool launch through the **literal cim-gui MCP server over stdio**
    (not the in-process driver): initialize a ClientSession, then call the real
    ``sidecar_start_tool`` → ``browser_get_text`` / ``assert_text`` →
    ``browser_screenshot`` → ``sidecar_stop_tool`` MCP tools end-to-end.

    Returns {"ok", "url", "text_found", "shot", "tools_called", "error"}.
    This is the airtight "uses MCP for E2E" proof for the smoke scenario.
    """
    import asyncio as _asyncio
    import base64 as _b64
    import json as _json
    import time as _time

    async def _drive() -> dict:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from mcp.types import ImageContent, TextContent

        _port = base_url.rstrip("/").rsplit(":", 1)[-1] or "8765"
        env = {**os.environ, "PYTHONPATH": str(_MCP_PKG),
               "CIM_MCP_HEADLESS": "1", "CIM_MCP_TIMEOUT": "90000",
               "CIM_SIDECAR_PORT": _port}
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "cim_gui_mcp.server"],
            cwd=str(_MCP_PKG), env=env)
        called: list[str] = []

        def _text(res) -> str:
            out = []
            for c in res.content:
                if isinstance(c, TextContent):
                    out.append(c.text)
            return "\n".join(out)

        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                called.append("sidecar_start_tool")
                start = await session.call_tool("sidecar_start_tool",
                                                {"tool_id": tool_id})
                start_txt = _text(start)
                url = ""
                try:
                    url = _json.loads(start_txt).get("input_url", "")
                except Exception:  # noqa: BLE001
                    pass
                if not url:
                    return {"ok": False, "url": "", "text_found": False,
                            "shot": None, "tools_called": called,
                            "error": f"no url from start: {start_txt[:200]}"}
                # let the per-session Streamlit script render
                found = False
                for _ in range(60):
                    called.append("browser_get_text")
                    body = _text(await session.call_tool(
                        "browser_get_text", {"url": url}))
                    if expect_text in body:
                        found = True
                        break
                    await _asyncio.sleep(1.0)
                shot = None
                if shot_path:
                    called.append("browser_screenshot")
                    res = await session.call_tool("browser_screenshot",
                                                  {"url": url})
                    for c in res.content:
                        if isinstance(c, ImageContent):
                            Path(shot_path).parent.mkdir(parents=True, exist_ok=True)
                            Path(shot_path).write_bytes(_b64.b64decode(c.data))
                            shot = str(shot_path)
                called.append("sidecar_stop_tool")
                await session.call_tool("sidecar_stop_tool", {})
                return {"ok": found, "url": url, "text_found": found,
                        "shot": shot, "tools_called": called, "error": None}

    try:
        return _asyncio.run(_drive())
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "url": "", "text_found": False, "shot": None,
                "tools_called": [], "error": f"{type(exc).__name__}: {exc}"}
