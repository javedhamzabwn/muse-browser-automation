"""core/router.py — Multi-backend browser router (browser="auto") for Muse 3.0."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from core.backends.chrome_backend import ChromeBackend
from core.backends.obscura_backend import ObscuraBackend
from core.backends.playwright_backend import PlaywrightBackend
from core.interfaces import BaseBrowserBackend
from core.types import BrowserBackendType, PageModel

logger = logging.getLogger("muse.router")


class BrowserRouter:
    """Intelligent router selecting the fastest and most appropriate browser backend."""

    def __init__(
        self,
        chrome: Optional[ChromeBackend] = None,
        obscura: Optional[ObscuraBackend] = None,
        playwright: Optional[PlaywrightBackend] = None,
    ):
        self.backends: Dict[BrowserBackendType, BaseBrowserBackend] = {}
        self.backends[BrowserBackendType.CHROME] = chrome or ChromeBackend()
        self.backends[BrowserBackendType.OBSCURA] = obscura or ObscuraBackend()
        self.backends[BrowserBackendType.PLAYWRIGHT] = playwright or PlaywrightBackend()
        self._active_backend: Optional[BaseBrowserBackend] = None

    def register_backend(self, btype: BrowserBackendType, backend: BaseBrowserBackend) -> None:
        self.backends[btype] = backend

    async def get_available_backends(self) -> List[BrowserBackendType]:
        avail = []
        for btype, b in self.backends.items():
            if await b.is_available():
                avail.append(btype)
        return avail

    async def health_check(self) -> Dict[str, Any]:
        """Perform health and connectivity check across all registered backends."""
        status: Dict[str, Any] = {}
        for btype, b in self.backends.items():
            avail = await b.is_available()
            conn = await b.is_connected() if avail else False
            status[btype.value] = {"available": avail, "connected": conn}
        status["active_backend"] = self._active_backend.backend_type.value if self._active_backend else "none"
        return status

    async def resolve_backend(
        self,
        preference: str = "auto",
        intent: Optional[str] = None,
        session_required: bool = False,
        stealth_required: bool = False,
    ) -> BaseBrowserBackend:
        """Select backend using availability, performance, and task requirements."""
        pref = preference.lower()

        # Explicit override
        if pref == "moli":
            if BrowserBackendType.MOLI not in self.backends:
                from core.backends.moli_backend import MoliBackend
                self.backends[BrowserBackendType.MOLI] = MoliBackend()
            b = self.backends[BrowserBackendType.MOLI]
            if not await b.is_available(): raise RuntimeError("Moli not available")
            self._active_backend = b
            return b

        if pref == "camoufox":
            if BrowserBackendType.CAMOUFOX not in self.backends:
                from core.backends.camoufox_backend import CamoufoxBackend
                self.backends[BrowserBackendType.CAMOUFOX] = CamoufoxBackend()
            b = self.backends[BrowserBackendType.CAMOUFOX]
            if not await b.is_available(): raise RuntimeError("Camoufox not available")
            self._active_backend = b
            return b

        if pref == "agent-browser":
            if BrowserBackendType.AGENT_BROWSER not in self.backends:
                from core.backends.agent_browser_backend import AgentBrowserBackend
                self.backends[BrowserBackendType.AGENT_BROWSER] = AgentBrowserBackend()
            b = self.backends[BrowserBackendType.AGENT_BROWSER]
            if not await b.is_available(): raise RuntimeError("Agent-Browser not available")
            self._active_backend = b
            return b

        if pref in ("chrome", "csi", BrowserBackendType.CHROME.value):
            b = self.backends[BrowserBackendType.CHROME]
            if not await b.is_available():
                raise RuntimeError("Requested Chrome backend is not available on this system.")
            self._active_backend = b
            return b

        if pref in ("obscura", BrowserBackendType.OBSCURA.value):
            b = self.backends[BrowserBackendType.OBSCURA]
            if not await b.is_available():
                raise RuntimeError("Requested Obscura backend is not available on this system.")
            self._active_backend = b
            return b

        if pref in ("playwright", BrowserBackendType.PLAYWRIGHT.value):
            b = self.backends[BrowserBackendType.PLAYWRIGHT]
            if not await b.is_available():
                raise RuntimeError("Requested Playwright backend is not available on this system.")
            self._active_backend = b
            return b

        # Intelligent 'auto' routing
        # 1. Personal session requirement -> Chrome
        if session_required:
            chrome = self.backends[BrowserBackendType.CHROME]
            if await chrome.is_connected():
                self._active_backend = chrome
                return chrome

        # 2. Stealth anti-detect requirement -> Obscura
        if stealth_required:
            obscura = self.backends[BrowserBackendType.OBSCURA]
            if await obscura.is_connected():
                self._active_backend = obscura
                return obscura

        # 3. Default fast path: Playwright (if installed) for isolated headless speed
        pw = self.backends[BrowserBackendType.PLAYWRIGHT]
        if await pw.is_available():
            self._active_backend = pw
            return pw

        # 4. Fallback to Chrome if available
        chrome = self.backends[BrowserBackendType.CHROME]
        if await chrome.is_available():
            self._active_backend = chrome
            return chrome

        # 5. Fallback to Obscura
        obscura = self.backends[BrowserBackendType.OBSCURA]
        if await obscura.is_available():
            self._active_backend = obscura
            return obscura

        raise RuntimeError("No browser backend is currently available on this machine.")

    # ── Unified Proxy Methods ──────────────────────────────────────────

    async def list_tabs(self, backend: Optional[BaseBrowserBackend] = None) -> List[Dict[str, Any]]:
        b = backend or self._active_backend or await self.resolve_backend()
        return await b.list_tabs()

    async def create_tab(self, url: str = "about:blank", backend: Optional[BaseBrowserBackend] = None) -> str:
        b = backend or self._active_backend or await self.resolve_backend()
        return await b.create_tab(url)

    async def switch_tab(self, tab_id: str, focus: bool = False, backend: Optional[BaseBrowserBackend] = None) -> None:
        b = backend or self._active_backend or await self.resolve_backend()
        await b.switch_tab(tab_id, focus=focus)

    async def close_tab(self, tab_id: str, backend: Optional[BaseBrowserBackend] = None) -> None:
        b = backend or self._active_backend or await self.resolve_backend()
        await b.close_tab(tab_id)

    async def navigate(self, tab_id: str, url: str, wait_until: str = "load", backend: Optional[BaseBrowserBackend] = None) -> bool:
        b = backend or self._active_backend or await self.resolve_backend()
        return await b.navigate(tab_id, url, wait_until)

    async def get_title(self, tab_id: str, backend: Optional[BaseBrowserBackend] = None) -> str:
        b = backend or self._active_backend or await self.resolve_backend()
        return await b.get_title(tab_id)

    async def get_url(self, tab_id: str, backend: Optional[BaseBrowserBackend] = None) -> str:
        b = backend or self._active_backend or await self.resolve_backend()
        return await b.get_url(tab_id)

    async def evaluate(self, tab_id: str, expression: str, backend: Optional[BaseBrowserBackend] = None) -> Any:
        b = backend or self._active_backend or await self.resolve_backend()
        return await b.evaluate(tab_id, expression)

    async def click(self, tab_id: str, x: int, y: int, backend: Optional[BaseBrowserBackend] = None) -> bool:
        b = backend or self._active_backend or await self.resolve_backend()
        return await b.click(tab_id, x, y)

    async def type_text(self, tab_id: str, text: str, backend: Optional[BaseBrowserBackend] = None) -> bool:
        b = backend or self._active_backend or await self.resolve_backend()
        return await b.type_text(tab_id, text)

    async def press_key(self, tab_id: str, key: str, backend: Optional[BaseBrowserBackend] = None) -> bool:
        b = backend or self._active_backend or await self.resolve_backend()
        return await b.press_key(tab_id, key)

    async def scroll(self, tab_id: str, delta_x: int = 0, delta_y: int = 400, backend: Optional[BaseBrowserBackend] = None) -> bool:
        b = backend or self._active_backend or await self.resolve_backend()
        return await b.scroll(tab_id, delta_x, delta_y)

    async def screenshot(self, tab_id: str, full_page: bool = False, backend: Optional[BaseBrowserBackend] = None) -> bytes:
        b = backend or self._active_backend or await self.resolve_backend()
        return await b.screenshot(tab_id, full_page)

    async def build_page_model(self, tab_id: str, backend: Optional[BaseBrowserBackend] = None) -> PageModel:
        b = backend or self._active_backend or await self.resolve_backend()
        return await b.build_page_model(tab_id)

    async def execute_action(
        self,
        tab_id: str,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        verify: bool = True,
        expected_change: Optional[str] = None,
        timeout_ms: int = 1000,
        backend: Optional[BaseBrowserBackend] = None,
    ) -> ActionResult:
        from core.types import ActionResult
        from core.verifier import ActionVerifier

        b = backend or self._active_backend or await self.resolve_backend()
        p = params or {}
        verifier = ActionVerifier()
        start = time.perf_counter()

        before_state: Dict[str, Any] = {}
        if verify:
            before_state = await verifier.capture_state(b, tab_id)

        ok = False
        error_msg = None
        data = None

        try:
            if action == "click":
                x, y = int(p.get("x", 0)), int(p.get("y", 0))
                ok = await b.click(tab_id, x, y)
            elif action == "type":
                text = str(p.get("text", ""))
                ok = await b.type_text(tab_id, text)
            elif action == "press":
                key = str(p.get("key", "Enter"))
                ok = await b.press_key(tab_id, key)
            elif action == "navigate":
                url = str(p.get("url", ""))
                ok = await b.navigate(tab_id, url)
            elif action == "scroll":
                dx, dy = int(p.get("delta_x", 0)), int(p.get("delta_y", 400))
                ok = await b.scroll(tab_id, dx, dy)
            else:
                raise ValueError(f"Unknown action: {action}")
        except Exception as exc:
            ok = False
            error_msg = str(exc)

        v_res = None
        if ok and verify:
            v_res = await verifier.verify_action(
                b,
                tab_id,
                action=action,
                before_state=before_state,
                expected_change=expected_change,
                timeout_ms=timeout_ms,
            )

        duration = (time.perf_counter() - start) * 1000.0
        return ActionResult(
            ok=ok,
            action=action,
            duration_ms=duration,
            verification=v_res,
            data=data,
            error=error_msg,
        )

