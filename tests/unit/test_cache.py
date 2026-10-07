"""tests/unit/test_cache.py — Unit tests for Phase 6 Self-Healing Selector Cache."""

import asyncio
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from core.backends.playwright_backend import PlaywrightBackend
from core.cache import SelectorCache
from core.resolver import ElementResolver
from core.types import ElementQuery, ResolutionMethod
from tests.synthetic_server import SyntheticServer


class TestSelectorCacheUnit(unittest.TestCase):
    def setUp(self):
        self.cache = SelectorCache(db_path=":memory:")

    def test_cache_put_get(self):
        self.assertIsNone(self.cache.get("example.com", "/login", "login_button"))
        self.cache.put("example.com", "/login", "login_button", "#submit-btn", "deterministic", 1.0)
        sel = self.cache.get("example.com", "/login", "login_button")
        self.assertEqual(sel, "#submit-btn")

    def test_cache_auto_decay_after_3_failures(self):
        self.cache.put("example.com", "/cart", "checkout", "#checkout-btn", "semantic", 0.95)
        self.assertEqual(self.cache.get("example.com", "/cart", "checkout"), "#checkout-btn")

        self.cache.record_failure("example.com", "/cart", "checkout")
        self.assertEqual(self.cache.get("example.com", "/cart", "checkout"), "#checkout-btn")

        self.cache.record_failure("example.com", "/cart", "checkout")
        self.cache.record_failure("example.com", "/cart", "checkout")
        # 3 failures -> decayed
        self.assertIsNone(self.cache.get("example.com", "/cart", "checkout"))

    def test_cache_heal(self):
        self.cache.put("example.com", "/settings", "save", "#old-save", "deterministic", 1.0)
        self.cache.record_failure("example.com", "/settings", "save")
        self.cache.record_failure("example.com", "/settings", "save")
        self.cache.record_failure("example.com", "/settings", "save")
        self.assertIsNone(self.cache.get("example.com", "/settings", "save"))

        # Heal with new selector
        self.cache.heal("example.com", "/settings", "save", "#new-save", "semantic", 0.98)
        self.assertEqual(self.cache.get("example.com", "/settings", "save"), "#new-save")

    def test_cache_stats_and_clear(self):
        self.cache.put("example.com", "/home", "search", "input.search", "deterministic", 1.0)
        stats = self.cache.stats()
        self.assertEqual(stats["total_entries"], 1)

        self.cache.clear()
        self.assertEqual(self.cache.stats()["total_entries"], 0)


class TestSelectorCacheIntegration(unittest.IsolatedAsyncioTestCase):
    server: SyntheticServer
    backend: PlaywrightBackend
    tab_id: str
    base_url: str

    async def asyncSetUp(self):
        self.server = SyntheticServer(port=18082)
        self.server.start()
        self.base_url = self.server.url

        self.backend = PlaywrightBackend(headless=True)
        await self.backend.start()
        tabs = await self.backend.list_tabs()
        self.tab_id = tabs[0]["tabId"]
        await self.backend.navigate(self.tab_id, f"{self.base_url}/synthetic.html")
        await asyncio.sleep(0.05)

    async def asyncTearDown(self):
        await self.backend.stop()
        self.server.stop()

    async def test_resolver_caching_and_self_healing(self):
        cache = SelectorCache(db_path=":memory:")
        resolver = ElementResolver(cache=cache)

        # 1. First resolution: uncached, resolves via SEMANTIC
        q1 = ElementQuery(name="Submit Order", role="button")
        res1 = await resolver.resolve(self.backend, self.tab_id, q1)
        self.assertIsNotNone(res1)
        self.assertEqual(res1.method, ResolutionMethod.SEMANTIC)

        # 2. Second resolution: cached! Resolves via CACHE in < 5ms
        t0 = time.perf_counter()
        res2 = await resolver.resolve(self.backend, self.tab_id, q1)
        cache_lat = (time.perf_counter() - t0) * 1000.0
        print(f"\n[Layer 0 Cache Resolution Latency] {cache_lat:.2f}ms")
        self.assertIsNotNone(res2)
        self.assertEqual(res2.method, ResolutionMethod.CACHE)
        self.assertLess(cache_lat, 20.0)

        # 3. Simulate website breaking change: change button ID in DOM
        await self.backend.evaluate(self.tab_id, """() => {
            const btn = document.getElementById('btn-dyn-84920');
            btn.id = 'btn-dyn-repaired-1122';
        }""")

        # 4. Third resolution: Cached selector fails, triggers self-healing, resolves via SEMANTIC
        res3 = await resolver.resolve(self.backend, self.tab_id, q1)
        self.assertIsNotNone(res3)
        self.assertEqual(res3.method, ResolutionMethod.SEMANTIC)
        self.assertIn("btn-dyn-repaired-1122", res3.selector)

        # 5. Fourth resolution: New healed selector is now cached and used
        res4 = await resolver.resolve(self.backend, self.tab_id, q1)
        self.assertIsNotNone(res4)
        self.assertEqual(res4.method, ResolutionMethod.CACHE)
        self.assertIn("btn-dyn-repaired-1122", res4.selector)


if __name__ == "__main__":
    unittest.main()
