from typing import Optional, Dict, Any, List
import uuid
import os
import subprocess
import asyncio
import urllib.request
import json
from .playwright_backend import PlaywrightBackend
from core.types import BrowserBackendType

class MoliBackend(PlaywrightBackend):
    """Adapter driving the Moli rust engine via Playwright connect_over_cdp."""
    
    def __init__(self, headless: bool = True):
        super().__init__(headless)
        self.port = 9226
        self.host = "127.0.0.1"
        self._moli_proc = None

    async def is_available(self) -> bool:
        exe = os.path.join("external", "moli", "moli.exe")
        return os.path.isfile(exe)

    async def is_connected(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    async def _is_moli_http_ready(self) -> bool:
        try:
            req = urllib.request.Request(f"http://{self.host}:{self.port}/json/version")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                data = json.loads(resp.read().decode())
                return "Browser" in data or "Protocol-Version" in data
        except Exception:
            return False

    async def start(self) -> None:
        if await self.is_connected():
            return
            
        exe = os.path.join("external", "moli", "moli.exe")
        if not os.path.isfile(exe):
            raise RuntimeError(f"Moli executable not found at {exe}")
            
        if not await self._is_moli_http_ready():
            self._moli_proc = subprocess.Popen(
                [exe, "serve", "--host", self.host, "--port", str(self.port), "--layout"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            # Wait for it to become ready
            for _ in range(30):
                if await self._is_moli_http_ready():
                    break
                await asyncio.sleep(0.5)
            else:
                raise RuntimeError(f"Moli did not start on port {self.port}")
                
        # Connect Playwright
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        
        try:
            req = urllib.request.Request(f"http://{self.host}:{self.port}/json/version")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                data = json.loads(resp.read().decode())
                ws_url = data.get("webSocketDebuggerUrl") or f"ws://{self.host}:{self.port}/devtools/browser"
        except Exception:
            ws_url = f"ws://{self.host}:{self.port}/devtools/browser"

        self._browser = await self._pw.chromium.connect_over_cdp(ws_url)
        self._context = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()
        
        # Moli usually comes with a default page
        pages = self._context.pages
        page = pages[0] if pages else await self._context.new_page()
        
        self._page_counter += 1
        tid = f"moli_{self._page_counter}"
        self._pages[tid] = page
        self._active_tab_id = tid

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None
        if self._moli_proc:
            self._moli_proc.terminate()
            self._moli_proc = None

    async def create_tab(self, url: str = "about:blank") -> str:
        page = await self._context.new_page()
        self._page_counter += 1
        tid = f"moli_{self._page_counter}"
        self._pages[tid] = page
        self._active_tab_id = tid
        if url and url != "about:blank":
            await page.goto(url)
        return tid
