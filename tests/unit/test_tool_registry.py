"""tests/unit/test_tool_registry.py — Unit tests for Phase 3/7 Tool Registry & Capabilities."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from core.tools.capabilities import CapabilityMatcher, ToolCapability
from core.tools.manifest import ToolCategory, ToolManifest, ToolStatus
from core.tools.registry import ToolRegistry


class TestToolRegistry(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        # Reset singleton
        ToolRegistry._instance = None
        self.registry = ToolRegistry(config_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        ToolRegistry._instance = None

    def test_default_catalog_registered(self):
        tools = self.registry.list_tools()
        names = {t.name for t in tools}
        self.assertIn("playwright", names)
        self.assertIn("chrome", names)
        self.assertIn("obscura", names)
        self.assertIn("moli", names)
        self.assertIn("lightpanda", names)
        self.assertIn("agent-browser", names)
        self.assertIn("camoufox", names)
        self.assertIn("csi", names)
        self.assertIn("http_static", names)
        self.assertIn("redlib", names)
        self.assertIn("yt-dlp", names)

    def test_detection_engine(self):
        self.registry.detect_all()
        # Playwright and http_static should be detected
        pw = self.registry.get_tool("playwright")
        self.assertIsNotNone(pw)
        self.assertTrue(pw.installed)

        http = self.registry.get_tool("http_static")
        self.assertIsNotNone(http)
        self.assertTrue(http.installed)

        obs = self.registry.get_tool("obscura")
        self.assertIsNotNone(obs)
        # Obscura was unpacked into ~/obscura
        self.assertTrue(obs.installed)

    def test_capability_matcher(self):
        self.registry.detect_all()
        # Require javascript + dom
        candidates = self.registry.find_capable({"javascript": True, "dom": True}, require_ready=False)
        names = [c.name for c in candidates]
        self.assertIn("playwright", names)
        self.assertIn("obscura", names)
        self.assertNotIn("http_static", names)

        # Require video_download
        video_candidates = self.registry.find_capable({"video_download": True}, require_ready=False)
        self.assertEqual(len(video_candidates), 1)
        self.assertEqual(video_candidates[0].name, "yt-dlp")

        # Preferred tool priority
        pref = self.registry.find_capable({"javascript": True}, require_ready=False, preferred_tool="obscura")
        self.assertEqual(pref[0].name, "obscura")

    def test_enable_disable_config_persistence(self):
        self.assertTrue(self.registry.set_enabled("playwright", False))
        pw = self.registry.get_tool("playwright")
        self.assertFalse(pw.enabled)

        # Reload from disk
        ToolRegistry._instance = None
        new_registry = ToolRegistry(config_dir=self.temp_dir)
        new_pw = new_registry.get_tool("playwright")
        self.assertFalse(new_pw.enabled)


if __name__ == "__main__":
    unittest.main()
