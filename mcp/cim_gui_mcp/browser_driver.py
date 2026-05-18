from __future__ import annotations

import base64
from typing import Optional

from playwright.async_api import (
    Browser,
    Page,
    Playwright,
    async_playwright,
)

from .config import BROWSER_HEADLESS, DEFAULT_TIMEOUT


class BrowserError(Exception):
    """Raised when a browser operation fails."""


class BrowserDriver:
    """
    Singleton Playwright Chromium browser.

    Pages are keyed by URL so repeated calls to the same URL reuse the
    existing page rather than opening a new one.  Call `close()` to shut
    down cleanly.
    """

    def __init__(
        self,
        headless: bool = BROWSER_HEADLESS,
        default_timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self._headless = headless
        self._default_timeout = default_timeout
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._pages: dict[str, Page] = {}

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._browser is not None:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)

    async def close(self, url: Optional[str] = None) -> str:
        if url:
            page = self._pages.pop(url, None)
            if page and not page.is_closed():
                await page.close()
            return f"closed: {url}"
        # Close all
        for page in list(self._pages.values()):
            if not page.is_closed():
                await page.close()
        self._pages.clear()
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        return "closed all"

    # ── Page management ───────────────────────────────────────────────────

    async def get_page(self, url: str) -> Page:
        await self.start()
        existing = self._pages.get(url)
        if existing and not existing.is_closed():
            return existing
        page = await self._browser.new_page()
        page.set_default_timeout(self._default_timeout)
        await page.goto(url, wait_until="networkidle")
        self._pages[url] = page
        return page

    # ── Actions ───────────────────────────────────────────────────────────

    async def screenshot(self, url: str, full_page: bool = False) -> bytes:
        page = await self.get_page(url)
        return await page.screenshot(full_page=full_page)

    async def screenshot_b64(self, url: str, full_page: bool = False) -> str:
        raw = await self.screenshot(url, full_page)
        return base64.b64encode(raw).decode("ascii")

    async def click(self, url: str, selector: str, timeout: Optional[int] = None) -> None:
        page = await self.get_page(url)
        try:
            await page.click(selector, timeout=timeout or self._default_timeout)
        except Exception as exc:
            raise BrowserError(f"click({selector!r}) failed: {exc}") from exc

    async def fill(self, url: str, selector: str, value: str, timeout: Optional[int] = None) -> None:
        page = await self.get_page(url)
        try:
            await page.fill(selector, value, timeout=timeout or self._default_timeout)
        except Exception as exc:
            raise BrowserError(f"fill({selector!r}) failed: {exc}") from exc

    async def get_text(self, url: str, selector: Optional[str] = None) -> str:
        page = await self.get_page(url)
        if selector:
            try:
                return await page.inner_text(selector)
            except Exception as exc:
                raise BrowserError(f"get_text({selector!r}) failed: {exc}") from exc
        return await page.inner_text("body")

    async def wait_for(
        self,
        url: str,
        selector: str,
        state: str = "visible",
        timeout: Optional[int] = None,
    ) -> None:
        page = await self.get_page(url)
        try:
            await page.wait_for_selector(
                selector,
                state=state,  # type: ignore[arg-type]
                timeout=timeout or self._default_timeout,
            )
        except Exception as exc:
            raise BrowserError(f"wait_for({selector!r}, state={state!r}) timed out: {exc}") from exc

    # ── Assertions ────────────────────────────────────────────────────────

    async def is_visible(self, url: str, selector: str) -> bool:
        page = await self.get_page(url)
        try:
            return await page.is_visible(selector)
        except Exception:
            return False

    async def find_errors(self, url: str) -> list[str]:
        """Return text of any Streamlit error/warning alert boxes."""
        page = await self.get_page(url)
        errors: list[str] = []
        # Streamlit renders errors in div[data-testid="stNotification"] or .stAlert
        for sel in ('[data-testid="stNotification"]', ".stAlert", '[role="alert"]'):
            try:
                elements = await page.query_selector_all(sel)
                for el in elements:
                    text = (await el.inner_text()).strip()
                    if text:
                        errors.append(text)
            except Exception:
                pass
        return errors


# Module-level singleton used by the MCP server
_driver: Optional[BrowserDriver] = None


def get_driver() -> BrowserDriver:
    global _driver
    if _driver is None:
        _driver = BrowserDriver()
    return _driver
