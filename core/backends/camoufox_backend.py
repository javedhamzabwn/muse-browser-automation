from typing import Optional, Dict, Any, List
import uuid
from .playwright_backend import PlaywrightBackend
from core.types import BrowserBackendType

class CamoufoxBackend(PlaywrightBackend):
    """Adapter driving the Camoufox anti-detect browser via Playwright."""
    
    # We can override backend_type if we added CAMOUFOX to BrowserBackendType, but PLAYWRIGHT works fine for type-checking.

    async def is_available(self) -> bool:
        try:
            import camoufox
            return True
        except ImportError:
            return False

    async def start(self) -> None:
        if self._browser and self._browser.is_connected():
            return
        
        from camoufox.async_api import AsyncCamoufox
        # AsyncCamoufox acts like a browser context in Playwright
        import os
        os.makedirs('.openmuse/camoufox', exist_ok=True)
        self._camoufox_instance = AsyncCamoufox(
            headless=self.headless,
            addons=[],
            persistent_context=True,
            user_data_dir=os.path.abspath('.openmuse/camoufox')
        )
        self._context = await self._camoufox_instance.__aenter__()
        self._browser = self._context  # Alias for compatibility checks
        
        page = await self._context.new_page()
        self._page_counter += 1
        tid = f"cfx_{self._page_counter}"
        self._pages[tid] = page
        self._active_tab_id = tid

    async def stop(self) -> None:
        if self._context:
            await self._context.close()
            self._context = None
            self._browser = None

    async def create_tab(self, url: str = "about:blank") -> str:
        page = await self._context.new_page()
        self._page_counter += 1
        tid = f"cfx_{self._page_counter}"
        self._pages[tid] = page
        self._active_tab_id = tid
        if url and url != "about:blank":
            await page.goto(url)
        return tid
