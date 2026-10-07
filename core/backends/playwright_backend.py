"""core/backends/playwright_backend.py — Isolated Playwright backend for Muse 3.0."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from core.interfaces import BaseBrowserBackend
from core.types import BrowserBackendType, ElementBounds, PageModel, ResolutionMethod, ResolvedElement


class PlaywrightBackend(BaseBrowserBackend):
    """Adapter driving an isolated Chromium/WebKit browser via Playwright async API."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._pw: Optional[Any] = None
        self._browser: Optional[Any] = None
        self._context: Optional[Any] = None
        self._pages: Dict[str, Any] = {}
        self._active_tab_id: Optional[str] = None
        self._page_counter = 0

    @property
    def backend_type(self) -> BrowserBackendType:
        return BrowserBackendType.PLAYWRIGHT

    async def is_available(self) -> bool:
        try:
            from playwright.async_api import async_playwright  # noqa: F401
            return True
        except ImportError:
            return False

    async def is_connected(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    async def start(self) -> None:
        if self._browser and self._browser.is_connected():
            return
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,
        )
        page = await self._context.new_page()
        self._page_counter += 1
        tid = f"pw_{self._page_counter}"
        self._pages[tid] = page
        self._active_tab_id = tid

    async def stop(self) -> None:
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None
        self._pages.clear()

    async def ensure_active_page(self) -> Any:
        if not self._browser or not self._browser.is_connected() or not self._context:
            await self.start()
        if not self._pages:
            await self.create_tab()
        page = self._pages.get(self._active_tab_id or "")
        if not page and self._pages:
            tid, page = next(iter(self._pages.items()))
            self._active_tab_id = tid
        return page

    def _get_page(self, tab_id: str) -> Any:
        page = self._pages.get(tab_id or self._active_tab_id or "")
        if not page:
            if self._pages:
                tid, page = next(iter(self._pages.items()))
                self._active_tab_id = tid
                return page
            raise RuntimeError("No active Playwright page available")
        return page

    async def list_tabs(self) -> List[Dict[str, Any]]:
        tabs = []
        for tid, p in self._pages.items():
            tabs.append({
                "id": tid,
                "tabId": tid,
                "title": await p.title(),
                "url": p.url,
                "active": tid == self._active_tab_id,
            })
        return tabs

    async def create_tab(self, url: str = "about:blank") -> str:
        if not self._context:
            await self.start()
        page = await self._context.new_page()
        if url and url != "about:blank":
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=90000)
            except Exception:
                pass
        self._page_counter += 1
        tid = f"pw_{self._page_counter}"
        self._pages[tid] = page
        self._active_tab_id = tid
        return tid

    async def switch_tab(self, tab_id: str, focus: bool = False) -> None:
        if tab_id in self._pages:
            self._active_tab_id = tab_id
            if focus:
                await self._pages[tab_id].bring_to_front()

    async def close_tab(self, tab_id: str) -> None:
        page = self._pages.pop(tab_id, None)
        if page:
            await page.close()
            if self._active_tab_id == tab_id:
                self._active_tab_id = next(iter(self._pages.keys())) if self._pages else None

    async def navigate(self, tab_id: str, url: str, wait_until: str = "load") -> bool:
        if not self._pages or not self._browser or not self._browser.is_connected():
            await self.ensure_active_page()
        page = self._get_page(tab_id)
        # Event-driven wait with aggressive timeout and retry
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            logger.warning("Playwright navigation timeout: %s. Retrying...", e)
            import asyncio
            await asyncio.sleep(2)
            await page.goto(url, wait_until="domcontentloaded", timeout=90000)
        return True

    async def get_title(self, tab_id: str) -> str:
        return await self._get_page(tab_id).title()

    async def get_url(self, tab_id: str) -> str:
        return self._get_page(tab_id).url

    async def evaluate(self, tab_id: str, expression: str) -> Any:
        return await self._get_page(tab_id).evaluate(expression)

    async def click(self, tab_id: str, x: int, y: int) -> bool:
        page = self._get_page(tab_id)
        await page.mouse.click(x, y)
        return True

    async def type_text(self, tab_id: str, text: str) -> bool:
        page = self._get_page(tab_id)
        await page.keyboard.type(text)
        return True

    async def press_key(self, tab_id: str, key: str) -> bool:
        page = self._get_page(tab_id)
        await page.keyboard.press(key)
        return True

    async def scroll(self, tab_id: str, delta_x: int = 0, delta_y: int = 400) -> bool:
        page = self._get_page(tab_id)
        try:
            await page.evaluate(f"window.scrollBy({delta_x}, {delta_y})")
        except Exception as e:
            logger.error("SCROLL EXCEPTION: %s", e)
            await page.mouse.wheel(delta_x, delta_y)
        return True

    async def screenshot(self, tab_id: str, full_page: bool = False) -> bytes:
        page = self._get_page(tab_id)
        return await page.screenshot(full_page=full_page)

    async def build_page_model(self, tab_id: str) -> PageModel:
        from core.page_model import PageModeler
        return await PageModeler.build(self, tab_id)

    async def get_cookies(self, tab_id: str) -> List[Dict[str, Any]]:
        if not self._context:
            return []
        return await self._context.cookies()

    async def set_cookies(self, tab_id: str, cookies: List[Dict[str, Any]]) -> bool:
        if not self._context:
            return False
        await self._context.add_cookies(cookies)
        return True
