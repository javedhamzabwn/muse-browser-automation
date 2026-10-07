"""tests/unit/test_resolver.py — Unit & integration tests for ElementResolver."""

import os
import unittest

from core.backends.playwright_backend import PlaywrightBackend
from core.resolver import ElementResolver
from core.types import ElementQuery, ResolutionMethod
from tests.synthetic_server import SyntheticServer


class TestElementResolverMock(unittest.IsolatedAsyncioTestCase):
    async def test_resolver_deterministic_match(self):
        # Test mock backend returning deterministic match
        from unittest.mock import AsyncMock, MagicMock
        backend = MagicMock()
        backend.evaluate = AsyncMock(return_value={
            "found": True,
            "method": "deterministic",
            "confidence": 1.0,
            "tag": "button",
            "role": "button",
            "name": "Submit",
            "selector": "#btn-submit",
            "bounds": {"x": 10, "y": 20, "w": 80, "h": 30},
            "in_shadow_dom": False
        })
        resolver = ElementResolver()
        el = await resolver.resolve(backend, "tab_1", ElementQuery(selector="#btn-submit"))
        self.assertIsNotNone(el)
        self.assertEqual(el.method, ResolutionMethod.DETERMINISTIC)
        self.assertEqual(el.bounds.center_x, 50)
        self.assertEqual(el.confidence, 1.0)

    async def test_resolver_semantic_match(self):
        from unittest.mock import AsyncMock, MagicMock
        backend = MagicMock()
        backend.evaluate = AsyncMock(return_value={
            "found": True,
            "method": "semantic",
            "confidence": 0.95,
            "tag": "button",
            "role": "button",
            "name": "Submit Order",
            "selector": "#btn-dyn-84920",
            "bounds": {"x": 25, "y": 50, "w": 120, "h": 40},
            "in_shadow_dom": False
        })
        resolver = ElementResolver()
        el = await resolver.resolve(backend, "tab_1", ElementQuery(role="button", name="Submit Order"))
        self.assertIsNotNone(el)
        self.assertEqual(el.method, ResolutionMethod.SEMANTIC)
        self.assertEqual(el.name, "Submit Order")
        self.assertEqual(el.confidence, 0.95)

    async def test_resolver_not_found(self):
        from unittest.mock import AsyncMock, MagicMock
        backend = MagicMock()
        backend.evaluate = AsyncMock(return_value={"found": False, "candidate_count": 5})
        resolver = ElementResolver(vision_fallback_enabled=False)
        el = await resolver.resolve(backend, "tab_1", ElementQuery(role="button", name="Nonexistent"))
        self.assertIsNone(el)


class TestElementResolverLive(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = SyntheticServer(port=18099)
        cls.base_url = cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    async def asyncSetUp(self):
        self.backend = PlaywrightBackend(headless=True)
        await self.backend.start()
        self.tab_id = await self.backend.create_tab(f"{self.base_url}/synthetic.html")
        self.resolver = ElementResolver()

    async def asyncTearDown(self):
        await self.backend.stop()

    async def test_layer1_deterministic_resolution(self):
        # Resolve via exact CSS ID selector
        el = await self.resolver.resolve(self.backend, self.tab_id, ElementQuery(selector="#btn-dyn-84920"))
        self.assertIsNotNone(el)
        self.assertEqual(el.method, ResolutionMethod.DETERMINISTIC)
        self.assertEqual(el.tag, "button")
        self.assertEqual(el.confidence, 1.0)

    async def test_layer2_semantic_dynamic_id_resolution(self):
        # Resolve dynamic button purely by role + text without using dynamic ID!
        el = await self.resolver.resolve(self.backend, self.tab_id, ElementQuery(role="button", text="Submit Order"))
        self.assertIsNotNone(el)
        self.assertEqual(el.method, ResolutionMethod.SEMANTIC)
        self.assertEqual(el.name, "Submit Order")
        self.assertGreaterEqual(el.confidence, 0.8)

    async def test_layer2_accessible_name_resolution(self):
        # Resolve via aria-label
        el = await self.resolver.resolve(self.backend, self.tab_id, ElementQuery(role="button", aria_label="Confirm Purchase"))
        self.assertIsNotNone(el)
        self.assertEqual(el.method, ResolutionMethod.SEMANTIC)
        self.assertIn("Confirm Purchase", el.name)

    async def test_layer2_shadow_dom_resolution(self):
        # Resolve element hidden inside Open Shadow Root!
        el = await self.resolver.resolve(self.backend, self.tab_id, ElementQuery(role="button", text="Shadow Save"))
        self.assertIsNotNone(el)
        self.assertEqual(el.method, ResolutionMethod.SEMANTIC)
        self.assertEqual(el.name, "Shadow Save")
        self.assertTrue(el.in_shadow_dom)


if __name__ == "__main__":
    unittest.main()
