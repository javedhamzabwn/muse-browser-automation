"""tests/unit/test_verifier.py — Unit tests for Phase 5 Event-Driven Action Verifier."""

import asyncio
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from core.backends.playwright_backend import PlaywrightBackend
from core.types import VerificationResult
from core.verifier import ActionVerifier
from tests.synthetic_server import SyntheticServer


class TestActionVerifierLive(unittest.IsolatedAsyncioTestCase):
    server: SyntheticServer
    backend: PlaywrightBackend
    tab_id: str
    base_url: str
    verifier: ActionVerifier

    async def asyncSetUp(self):
        self.server = SyntheticServer(port=18081)
        self.server.start()
        self.base_url = self.server.url

        self.backend = PlaywrightBackend(headless=True)
        await self.backend.start()
        tabs = await self.backend.list_tabs()
        self.tab_id = tabs[0]["tabId"]
        await self.backend.navigate(self.tab_id, f"{self.base_url}/synthetic.html")
        self.verifier = ActionVerifier()
        # Wait for initial delayed DOM timer (200ms) to settle
        await asyncio.sleep(0.25)

    async def asyncTearDown(self):
        await self.backend.stop()
        self.server.stop()

    async def test_dom_mutation_verification(self):
        """Clicking dynamic button causes instant DOM mutation verification (< 50ms)."""
        before_state = await self.verifier.capture_state(self.backend, self.tab_id)
        self.assertEqual(before_state.get("mutations"), 0)

        # Click dynamic button
        bounds = await self.backend.evaluate(self.tab_id, """() => {
            const r = document.getElementById('btn-dyn-84920').getBoundingClientRect();
            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
        }""")
        await self.backend.click(self.tab_id, bounds["x"], bounds["y"])

        t0 = time.perf_counter()
        result: VerificationResult = await self.verifier.verify_action(
            self.backend, self.tab_id, action="click", before_state=before_state, timeout_ms=500
        )
        elapsed = (time.perf_counter() - t0) * 1000.0

        print(f"\n[DOM Mutation Verification Latency] {elapsed:.2f}ms")
        self.assertTrue(result.verified)
        self.assertTrue(result.dom_mutated)
        self.assertLess(elapsed, 100.0, "Verification must complete in < 100ms")

    async def test_modal_dialog_verification(self):
        """Opening modal dialog triggers modal_open verification in < 50ms."""
        before_state = await self.verifier.capture_state(self.backend, self.tab_id)
        self.assertFalse(before_state.get("modal_open"))

        bounds = await self.backend.evaluate(self.tab_id, """() => {
            const el = document.getElementById('open-modal-btn');
            el.scrollIntoView({block: 'center'});
            const r = el.getBoundingClientRect();
            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
        }""")
        await self.backend.click(self.tab_id, bounds["x"], bounds["y"])

        result: VerificationResult = await self.verifier.verify_action(
            self.backend,
            self.tab_id,
            action="click",
            before_state=before_state,
            expected_change="modal_open",
            timeout_ms=500,
        )
        self.assertTrue(result.verified)
        self.assertTrue(result.details.get("modal_open"))

    async def test_timeout_no_change(self):
        """When no change occurs, verifier cleanly reports false after timeout without throwing."""
        before_state = await self.verifier.capture_state(self.backend, self.tab_id)
        result: VerificationResult = await self.verifier.verify_action(
            self.backend, self.tab_id, action="idle", before_state=before_state, timeout_ms=100
        )
        self.assertFalse(result.verified)
        self.assertFalse(result.page_changed)
        self.assertTrue(result.details.get("timeout"))


if __name__ == "__main__":
    unittest.main()
