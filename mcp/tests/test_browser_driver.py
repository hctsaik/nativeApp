from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cim_gui_mcp.browser_driver import BrowserDriver, BrowserError


@pytest.fixture
def driver() -> BrowserDriver:
    return BrowserDriver(headless=True, default_timeout=5000)


def _mock_page(closed: bool = False) -> AsyncMock:
    """Create a mock Playwright Page.
    is_closed() is synchronous in Playwright, so we use MagicMock for it.
    set_default_timeout() is also sync.
    """
    page = AsyncMock()
    page.is_closed = MagicMock(return_value=closed)
    page.set_default_timeout = MagicMock()
    return page


# ── Lifecycle ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_idempotent(driver: BrowserDriver):
    mock_browser = MagicMock()
    driver._browser = mock_browser
    await driver.start()
    assert driver._browser is mock_browser


@pytest.mark.asyncio
async def test_close_all(driver: BrowserDriver):
    mock_page = _mock_page(closed=False)
    mock_browser = AsyncMock()
    mock_pw = AsyncMock()

    driver._browser = mock_browser
    driver._playwright = mock_pw
    driver._pages = {"http://localhost:1234": mock_page}

    result = await driver.close()

    mock_page.close.assert_called_once()
    mock_browser.close.assert_called_once()
    mock_pw.stop.assert_called_once()
    assert result == "closed all"
    assert driver._pages == {}
    assert driver._browser is None
    assert driver._playwright is None


@pytest.mark.asyncio
async def test_close_single_url(driver: BrowserDriver):
    mock_page_a = _mock_page(closed=False)
    mock_page_b = _mock_page(closed=False)

    driver._pages = {
        "http://localhost:1234": mock_page_a,
        "http://localhost:5678": mock_page_b,
    }

    result = await driver.close("http://localhost:1234")

    mock_page_a.close.assert_called_once()
    mock_page_b.close.assert_not_called()
    assert "http://localhost:1234" not in driver._pages
    assert "http://localhost:5678" in driver._pages
    assert "closed: http://localhost:1234" in result


@pytest.mark.asyncio
async def test_close_already_closed_page(driver: BrowserDriver):
    mock_page = _mock_page(closed=True)
    driver._browser = AsyncMock()
    driver._playwright = AsyncMock()
    driver._pages = {"http://localhost:1234": mock_page}

    await driver.close()
    mock_page.close.assert_not_called()  # already closed, skip


# ── driver_with_page fixture ──────────────────────────────────────────────────


URL = "http://localhost:9999"


@pytest.fixture
def driver_with_page(driver: BrowserDriver):
    """BrowserDriver with a pre-configured mock page (no real browser needed)."""
    mock_page = _mock_page(closed=False)
    driver._pages[URL] = mock_page
    driver._browser = AsyncMock()  # prevent start() from launching real browser
    return driver, mock_page, URL


# ── Actions ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_screenshot_calls_page(driver_with_page):
    driver, mock_page, url = driver_with_page
    mock_page.screenshot = AsyncMock(return_value=b"PNG_DATA")
    result = await driver.screenshot(url)
    assert result == b"PNG_DATA"
    mock_page.screenshot.assert_called_once_with(full_page=False)


@pytest.mark.asyncio
async def test_screenshot_full_page(driver_with_page):
    driver, mock_page, url = driver_with_page
    mock_page.screenshot = AsyncMock(return_value=b"PNG_FULL")
    await driver.screenshot(url, full_page=True)
    mock_page.screenshot.assert_called_once_with(full_page=True)


@pytest.mark.asyncio
async def test_screenshot_b64_is_base64(driver_with_page):
    import base64
    driver, mock_page, url = driver_with_page
    mock_page.screenshot = AsyncMock(return_value=b"PNG")
    result = await driver.screenshot_b64(url)
    assert base64.b64decode(result) == b"PNG"


@pytest.mark.asyncio
async def test_click_calls_page(driver_with_page):
    driver, mock_page, url = driver_with_page
    await driver.click(url, "text=▶ 執行")
    mock_page.click.assert_called_once()


@pytest.mark.asyncio
async def test_click_passes_timeout(driver_with_page):
    driver, mock_page, url = driver_with_page
    await driver.click(url, ".btn", timeout=3000)
    mock_page.click.assert_called_once_with(".btn", timeout=3000)


@pytest.mark.asyncio
async def test_click_raises_browser_error_on_failure(driver_with_page):
    driver, mock_page, url = driver_with_page
    mock_page.click = AsyncMock(side_effect=Exception("Element not found"))
    with pytest.raises(BrowserError, match="click"):
        await driver.click(url, "text=missing")


@pytest.mark.asyncio
async def test_fill_calls_page(driver_with_page):
    driver, mock_page, url = driver_with_page
    await driver.fill(url, "input[type=text]", "hello")
    mock_page.fill.assert_called_once_with("input[type=text]", "hello", timeout=5000)


@pytest.mark.asyncio
async def test_fill_raises_browser_error_on_failure(driver_with_page):
    driver, mock_page, url = driver_with_page
    mock_page.fill = AsyncMock(side_effect=Exception("No such element"))
    with pytest.raises(BrowserError, match="fill"):
        await driver.fill(url, "bad-selector", "text")


@pytest.mark.asyncio
async def test_get_text_full_page(driver_with_page):
    driver, mock_page, url = driver_with_page
    mock_page.inner_text = AsyncMock(return_value="page content")
    result = await driver.get_text(url)
    mock_page.inner_text.assert_called_with("body")
    assert result == "page content"


@pytest.mark.asyncio
async def test_get_text_with_selector(driver_with_page):
    driver, mock_page, url = driver_with_page
    mock_page.inner_text = AsyncMock(return_value="element text")
    result = await driver.get_text(url, ".some-class")
    mock_page.inner_text.assert_called_with(".some-class")
    assert result == "element text"


@pytest.mark.asyncio
async def test_get_text_raises_browser_error(driver_with_page):
    driver, mock_page, url = driver_with_page
    mock_page.inner_text = AsyncMock(side_effect=Exception("selector missing"))
    with pytest.raises(BrowserError, match="get_text"):
        await driver.get_text(url, ".nope")


@pytest.mark.asyncio
async def test_wait_for_calls_page(driver_with_page):
    driver, mock_page, url = driver_with_page
    await driver.wait_for(url, ".stSuccess")
    mock_page.wait_for_selector.assert_called_once_with(
        ".stSuccess", state="visible", timeout=5000
    )


@pytest.mark.asyncio
async def test_wait_for_raises_on_timeout(driver_with_page):
    driver, mock_page, url = driver_with_page
    mock_page.wait_for_selector = AsyncMock(side_effect=Exception("Timeout"))
    with pytest.raises(BrowserError, match="timed out"):
        await driver.wait_for(url, ".missing")


# ── Assertions ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_is_visible_true(driver_with_page):
    driver, mock_page, url = driver_with_page
    mock_page.is_visible = AsyncMock(return_value=True)
    assert await driver.is_visible(url, ".stSuccess") is True


@pytest.mark.asyncio
async def test_is_visible_false(driver_with_page):
    driver, mock_page, url = driver_with_page
    mock_page.is_visible = AsyncMock(return_value=False)
    assert await driver.is_visible(url, ".missing") is False


@pytest.mark.asyncio
async def test_is_visible_exception_returns_false(driver_with_page):
    driver, mock_page, url = driver_with_page
    mock_page.is_visible = AsyncMock(side_effect=Exception("page closed"))
    assert await driver.is_visible(url, ".anything") is False


@pytest.mark.asyncio
async def test_find_errors_empty(driver_with_page):
    driver, mock_page, url = driver_with_page
    mock_page.query_selector_all = AsyncMock(return_value=[])
    errors = await driver.find_errors(url)
    assert errors == []


@pytest.mark.asyncio
async def test_find_errors_found(driver_with_page):
    driver, mock_page, url = driver_with_page
    mock_el = AsyncMock()
    mock_el.inner_text = AsyncMock(return_value="Something went wrong")

    async def _query(sel: str):
        return [mock_el] if "Notification" in sel else []

    mock_page.query_selector_all = _query
    errors = await driver.find_errors(url)
    assert "Something went wrong" in errors


@pytest.mark.asyncio
async def test_find_errors_ignores_empty_text(driver_with_page):
    driver, mock_page, url = driver_with_page
    mock_el = AsyncMock()
    mock_el.inner_text = AsyncMock(return_value="   ")  # whitespace only

    async def _query(sel: str):
        return [mock_el] if "Notification" in sel else []

    mock_page.query_selector_all = _query
    errors = await driver.find_errors(url)
    assert errors == []


# ── get_driver singleton ──────────────────────────────────────────────────────


def test_get_driver_returns_same_instance():
    from cim_gui_mcp.browser_driver import get_driver
    import cim_gui_mcp.browser_driver as mod
    mod._driver = None
    d1 = get_driver()
    d2 = get_driver()
    assert d1 is d2
    mod._driver = None  # reset
