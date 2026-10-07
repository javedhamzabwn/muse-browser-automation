"""tests/unit/test_risk_observability.py — Unit tests for Phase 9 Risk Engine & Observability."""

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from core.backends.playwright_backend import PlaywrightBackend
from core.observability import ActionTracer, CaptchaDetector
from core.risk_engine import RiskEngine
from core.types import ActionRiskLevel, ElementBounds, ResolutionMethod, ResolvedElement
from tests.synthetic_server import SyntheticServer


class TestRiskEngine(unittest.IsolatedAsyncioTestCase):
    def test_risk_classification(self):
        engine = RiskEngine()

        # Low risk: navigation, screenshot
        self.assertEqual(engine.assess_risk("navigate", "https://example.com"), ActionRiskLevel.LOW)
        self.assertEqual(engine.assess_risk("screenshot", "https://example.com"), ActionRiskLevel.LOW)

        # Medium risk: standard click
        el_ok = ResolvedElement(
            ref="e1", tag="button", role="button", name="Next Page",
            bounds=ElementBounds(0, 0, 10, 10), selector="#next",
            method=ResolutionMethod.DETERMINISTIC, confidence=1.0,
        )
        self.assertEqual(engine.assess_risk("click", "https://example.com", element=el_ok), ActionRiskLevel.MEDIUM)

        # High risk: dangerous action text
        el_danger = ResolvedElement(
            ref="e2", tag="button", role="button", name="Delete Account Permanently",
            bounds=ElementBounds(0, 0, 10, 10), selector="#del",
            method=ResolutionMethod.DETERMINISTIC, confidence=1.0,
        )
        self.assertEqual(engine.assess_risk("click", "https://example.com", element=el_danger), ActionRiskLevel.HIGH)

        # Critical risk: payment URL
        self.assertEqual(engine.assess_risk("click", "https://bank.com/checkout/pay"), ActionRiskLevel.CRITICAL)

    async def test_approval_gate_and_dry_run(self):
        approved = False

        async def mock_gate(payload):
            return approved

        engine = RiskEngine(max_auto_risk=ActionRiskLevel.MEDIUM, approval_hook=mock_gate)
        el_danger = ResolvedElement(
            ref="e2", tag="button", role="button", name="Purchase Product Now",
            bounds=ElementBounds(0, 0, 10, 10), selector="#buy",
            method=ResolutionMethod.DETERMINISTIC, confidence=1.0,
        )

        # Disapproved
        self.assertFalse(await engine.verify_permission("click", "https://shop.com", element=el_danger))

        # Approved
        approved = True
        self.assertTrue(await engine.verify_permission("click", "https://shop.com", element=el_danger))

        # Dry run always blocks mutation
        dry_engine = RiskEngine(dry_run=True)
        self.assertFalse(await dry_engine.verify_permission("click", "https://example.com"))
        self.assertTrue(await dry_engine.verify_permission("read", "https://example.com"))


class TestObservability(unittest.IsolatedAsyncioTestCase):
    server: SyntheticServer
    backend: PlaywrightBackend
    tab_id: str
    base_url: str

    async def asyncSetUp(self):
        self.server = SyntheticServer(port=18084)
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

    def test_action_tracer_buffer(self):
        tracer = ActionTracer(capacity=3)
        tracer.record("click", 12.5, True, "tab1")
        tracer.record("type", 8.2, True, "tab1")
        tracer.record("navigate", 22.0, True, "tab1")
        tracer.record("scroll", 4.1, True, "tab1")  # Should evict oldest ('click')

        recent = tracer.get_recent(limit=10)
        self.assertEqual(len(recent), 3)
        self.assertEqual(recent[0]["action"], "type")
        self.assertEqual(recent[-1]["action"], "scroll")

    async def test_captcha_detector(self):
        res = await CaptchaDetector.detect(self.backend, self.tab_id)
        self.assertFalse(res["detected"])
        self.assertIsNone(res["type"])


if __name__ == "__main__":
    unittest.main()
