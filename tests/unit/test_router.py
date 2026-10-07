"""tests/unit/test_router.py — Unit tests for BrowserRouter."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from core.interfaces import BaseBrowserBackend
from core.router import BrowserRouter
from core.types import BrowserBackendType


class DummyBackend(BaseBrowserBackend):
    def __init__(self, btype: BrowserBackendType, available: bool = True, connected: bool = True):
        self._type = btype
        self._available = available
        self._connected = connected

    @property
    def backend_type(self) -> BrowserBackendType:
        return self._type

    async def is_available(self) -> bool:
        return self._available

    async def is_connected(self) -> bool:
        return self._connected

    async def start(self) -> None: pass
    async def stop(self) -> None: pass
    async def list_tabs(self): return []
    async def create_tab(self, url="about:blank"): return "tab_1"
    async def switch_tab(self, tab_id, focus=False): pass
    async def close_tab(self, tab_id): pass
    async def navigate(self, tab_id, url, wait_until="load"): return True
    async def get_title(self, tab_id): return "Mock Title"
    async def get_url(self, tab_id): return "http://example.com"
    async def evaluate(self, tab_id, expression): return 42
    async def click(self, tab_id, x, y): return True
    async def type_text(self, tab_id, text): return True
    async def press_key(self, tab_id, key): return True
    async def scroll(self, tab_id, delta_x=0, delta_y=400): return True
    async def screenshot(self, tab_id, full_page=False): return b"fake_png"
    async def build_page_model(self, tab_id): return None
    async def get_cookies(self, tab_id): return []
    async def set_cookies(self, tab_id, cookies): return True


class TestBrowserRouter(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_routing(self):
        chrome = DummyBackend(BrowserBackendType.CHROME, available=True)
        obscura = DummyBackend(BrowserBackendType.OBSCURA, available=True)
        pw = DummyBackend(BrowserBackendType.PLAYWRIGHT, available=True)
        router = BrowserRouter(chrome=chrome, obscura=obscura, playwright=pw)

        b = await router.resolve_backend(preference="chrome")
        self.assertEqual(b.backend_type, BrowserBackendType.CHROME)

        b = await router.resolve_backend(preference="obscura")
        self.assertEqual(b.backend_type, BrowserBackendType.OBSCURA)

        b = await router.resolve_backend(preference="playwright")
        self.assertEqual(b.backend_type, BrowserBackendType.PLAYWRIGHT)

    async def test_auto_routing_session_required(self):
        chrome = DummyBackend(BrowserBackendType.CHROME, available=True, connected=True)
        pw = DummyBackend(BrowserBackendType.PLAYWRIGHT, available=True, connected=False)
        router = BrowserRouter(chrome=chrome, playwright=pw)

        b = await router.resolve_backend(preference="auto", session_required=True)
        self.assertEqual(b.backend_type, BrowserBackendType.CHROME)

    async def test_auto_routing_stealth_required(self):
        obscura = DummyBackend(BrowserBackendType.OBSCURA, available=True, connected=True)
        pw = DummyBackend(BrowserBackendType.PLAYWRIGHT, available=True, connected=False)
        router = BrowserRouter(obscura=obscura, playwright=pw)

        b = await router.resolve_backend(preference="auto", stealth_required=True)
        self.assertEqual(b.backend_type, BrowserBackendType.OBSCURA)

    async def test_auto_routing_default_fast_path(self):
        chrome = DummyBackend(BrowserBackendType.CHROME, available=True, connected=False)
        pw = DummyBackend(BrowserBackendType.PLAYWRIGHT, available=True, connected=False)
        router = BrowserRouter(chrome=chrome, playwright=pw)

        b = await router.resolve_backend(preference="auto")
        self.assertEqual(b.backend_type, BrowserBackendType.PLAYWRIGHT)

    async def test_unavailable_backend_error(self):
        chrome = DummyBackend(BrowserBackendType.CHROME, available=False)
        router = BrowserRouter(chrome=chrome)
        with self.assertRaises(RuntimeError):
            await router.resolve_backend(preference="chrome")

    async def test_unified_proxy_calls(self):
        chrome = DummyBackend(BrowserBackendType.CHROME, available=True)
        router = BrowserRouter(chrome=chrome)
        await router.resolve_backend(preference="chrome")

        title = await router.get_title("tab_1")
        self.assertEqual(title, "Mock Title")
        tab_id = await router.create_tab("https://test.local")
        self.assertEqual(tab_id, "tab_1")


if __name__ == "__main__":
    unittest.main()
