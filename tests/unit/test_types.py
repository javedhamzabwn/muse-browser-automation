"""tests/unit/test_types.py — Unit tests for core/types.py."""

import unittest

from core.types import (
    ActionRiskLevel,
    ActionResult,
    BrowserBackendType,
    BrowserConfig,
    ElementBounds,
    ElementQuery,
    PageModel,
    ResolutionMethod,
    ResolvedElement,
    VerificationResult,
)


class TestCoreTypes(unittest.TestCase):
    def test_element_bounds_centers(self):
        bounds = ElementBounds(x=100, y=200, w=50, h=40)
        self.assertEqual(bounds.center_x, 125)
        self.assertEqual(bounds.center_y, 220)

    def test_resolved_element_to_dict(self):
        bounds = ElementBounds(x=10, y=20, w=100, h=30)
        elem = ResolvedElement(
            ref="e0",
            tag="button",
            role="button",
            name="Submit",
            bounds=bounds,
            selector="button#submit",
            method=ResolutionMethod.SEMANTIC,
            confidence=0.95,
            attributes={"id": "submit"},
        )
        d = elem.to_dict()
        self.assertEqual(d["ref"], "e0")
        self.assertEqual(d["method"], "semantic")
        self.assertEqual(d["bounds"]["center_x"], 60)
        self.assertEqual(d["bounds"]["center_y"], 35)

    def test_action_result_serialization(self):
        res = ActionResult(
            ok=True,
            action="click",
            duration_ms=42.126,
            verification=VerificationResult(verified=True, page_changed=True),
        )
        d = res.to_dict()
        self.assertTrue(d["ok"])
        self.assertEqual(d["duration_ms"], 42.13)
        self.assertTrue(d["verification"]["page_changed"])

    def test_page_model_compact(self):
        pm = PageModel(url="https://example.com", title="Example Domain")
        pm.buttons.append({"name": "More Info"})
        compact = pm.to_compact_dict()
        self.assertEqual(compact["buttons_count"], 1)
        self.assertEqual(compact["title"], "Example Domain")

    def test_browser_config_defaults(self):
        cfg = BrowserConfig()
        self.assertEqual(cfg.backend, BrowserBackendType.AUTO)
        self.assertEqual(cfg.cdp_port, 9222)
        self.assertEqual(cfg.risk_threshold, ActionRiskLevel.HIGH)


if __name__ == "__main__":
    unittest.main()
