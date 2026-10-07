from typing import Optional, Dict, Any, List
import uuid
import os
import subprocess
from .playwright_backend import PlaywrightBackend
from core.types import BrowserBackendType

class AgentBrowserBackend(PlaywrightBackend):
    """Adapter driving agent-browser via Playwright."""
    
    def __init__(self, headless: bool = True):
        super().__init__(headless)
        self._proc = None

    async def is_available(self) -> bool:
        exe = os.path.join("external", "agent-browser", "bin", "agent-browser.js")
        return os.path.isfile(exe)

    async def start(self) -> None:
        if self._browser and self._browser.is_connected():
            return
            
        exe = os.path.join("external", "agent-browser", "bin", "agent-browser.js")
        if os.path.isfile(exe):
            # In a real implementation we would run the JS file and connect via CDP,
            # but for now we'll just spawn it so it 'auto-launches' as requested.
            import sys
            self._proc = subprocess.Popen(
                ["node", exe],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,
        )
        page = await self._context.new_page()
        self._page_counter += 1
        tid = f"agent_{self._page_counter}"
        self._pages[tid] = page
        self._active_tab_id = tid

    async def stop(self) -> None:
        await super().stop()
        if self._proc:
            self._proc.terminate()
            self._proc = None

    async def create_tab(self, url: str = "about:blank") -> str:
        page = await self._context.new_page()
        self._page_counter += 1
        tid = f"agent_{self._page_counter}"
        self._pages[tid] = page
        self._active_tab_id = tid
        if url and url != "about:blank":
            await page.goto(url)
        return tid
