"""tests/unit/test_page_model.py — Unit tests for Phase 4 Zero-Shot Page Modeler."""

import asyncio
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from core.backends.playwright_backend import PlaywrightBackend
from core.types import PageModel
from tests.synthetic_server import SyntheticServer


class TestPageModel(unittest.IsolatedAsyncioTestCase):
    server: SyntheticServer
    backend: PlaywrightBackend
    tab_id: str
    base_url: str

    async def asyncSetUp(self):
        self.server = SyntheticServer(port=18080)
        self.server.start()
        self.base_url = self.server.url

        self.backend = PlaywrightBackend(headless=True)
        await self.backend.start()
        tabs = await self.backend.list_tabs()
        self.tab_id = tabs[0]["id"]
        await self.backend.navigate(self.tab_id, f"{self.base_url}/synthetic.html")
        await asyncio.sleep(0.05)

    async def asyncTearDown(self):
        await self.backend.stop()
        self.server.stop()

    async def test_page_model_extraction(self):
        """Verify complete extraction of DOM, Shadow DOM, iframes, and dialogs."""
        t0 = time.perf_counter()
        model: PageModel = await self.backend.build_page_model(self.tab_id)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        print(f"\n[PageModel Extraction Latency] {latency_ms:.2f}ms")
        self.assertLess(latency_ms, 100.0, "PageModel extraction must be < 100ms under load")
        self.assertIsInstance(model, PageModel)
        self.assertIn("Synthetic Test Suite", model.title)
        self.assertGreaterEqual(len(model.interactive_elements), 5)

        # 1. Check dynamic button
        dyn_btn = next((e for e in model.interactive_elements if "Submit Order" in e.name), None)
        self.assertIsNotNone(dyn_btn, "Submit Order button must be extracted")
        self.assertEqual(dyn_btn.tag, "button")

        # 2. Check Shadow DOM penetration
        shadow_btn = next((e for e in model.interactive_elements if "Shadow Save" in e.name), None)
        self.assertIsNotNone(shadow_btn, "Shadow DOM button must be extracted")
        self.assertTrue(shadow_btn.in_shadow_dom, "Element inside shadow root must have in_shadow_dom=True")

        # 3. Check Iframe traversal
        iframe_btn = next((e for e in model.interactive_elements if "Inside Frame Button" in e.name), None)
        self.assertIsNotNone(iframe_btn, "Button inside child iframe must be extracted")
        self.assertIsNotNone(iframe_btn.attributes.get("iframe_path"), "Iframe element must have iframe_path")

        # 4. Check Contenteditable
        editable = next((e for e in model.interactive_elements if e.tag == "contenteditable"), None)
        self.assertIsNotNone(editable, "Contenteditable element must be extracted")

        # 5. Check Dialog detection
        self.assertGreaterEqual(len(model.dialogs), 1, "Dialog element must be detected")
        dialog_entry = next((d for d in model.dialogs if d.get("id") == "test-dialog"), None)
        self.assertIsNotNone(dialog_entry, "test-dialog must be indexed in dialogs list")

        # 6. Verify Markdown and Dict serialization
        md = model.to_markdown()
        self.assertIn("Synthetic Test Suite", md)
        self.assertIn("Submit Order", md)
        self.assertIn("shadow-root", md)
        self.assertIn("iframe:", md)

        data = model.to_dict()
        self.assertEqual(data["title"], model.title)
        self.assertGreaterEqual(len(data["interactive_elements"]), 5)


if __name__ == "__main__":
    unittest.main()
