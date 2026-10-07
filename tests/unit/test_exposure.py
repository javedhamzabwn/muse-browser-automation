"""tests/unit/test_exposure.py — Unit tests for ExposureManager and PublicSecurityPolicy."""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from core.exposure.manager import DEFAULT_PORT, ExposureManager, ExposureMode, ExposureState
from core.exposure.security import CapabilityGroup, PublicSecurityPolicy


class TestExposureManager(unittest.TestCase):
    def setUp(self):
        # Reset singleton instance between tests
        ExposureManager._instance = None
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_file = os.path.join(self.temp_dir.name, "exposure.json")

    def tearDown(self):
        ExposureManager._instance = None
        self.temp_dir.cleanup()

    def test_default_port_and_urls(self):
        with patch.dict(os.environ, {}, clear=True):
            port = ExposureManager.resolve_gateway_port()
            self.assertEqual(port, DEFAULT_PORT)
            self.assertEqual(ExposureManager.get_local_url(port), f"http://127.0.0.1:{DEFAULT_PORT}")
            self.assertEqual(ExposureManager.get_local_mcp_url(port), f"http://127.0.0.1:{DEFAULT_PORT}/mcp")

    def test_custom_port_via_env(self):
        with patch.dict(os.environ, {"MUSE_PORT": "19050"}):
            port = ExposureManager.resolve_gateway_port()
            self.assertEqual(port, 19050)
            self.assertEqual(ExposureManager.get_local_url(port), "http://127.0.0.1:19050")
            self.assertEqual(ExposureManager.get_local_mcp_url(port), "http://127.0.0.1:19050/mcp")

    def test_exposure_modes(self):
        self.assertEqual(ExposureMode.LOCAL.value, "local")
        self.assertEqual(ExposureMode.NGROK.value, "ngrok")
        self.assertEqual(ExposureMode.BOTH.value, "both")
        self.assertEqual(ExposureMode.OFF.value, "off")

    def test_state_persistence_and_no_secrets(self):
        exp = ExposureManager(state_file=self.state_file)
        exp.state.mode = ExposureMode.LOCAL.value
        exp.state.public_url = None
        exp.save_state()

        self.assertTrue(os.path.exists(self.state_file))
        with open(self.state_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["mode"], "local")
        self.assertEqual(data["local_port"], DEFAULT_PORT)
        # Ensure zero passwords, tokens, or credentials stored
        for key in data.keys():
            self.assertNotIn("secret", key.lower())
            self.assertNotIn("password", key.lower())
            self.assertNotIn("token", key.lower())

    def test_is_port_listening_false_on_free_port(self):
        exp = ExposureManager(state_file=self.state_file)
        # Port 59871 is practically guaranteed to be unused
        self.assertFalse(exp.is_port_listening(59871))

    def test_status_structure(self):
        exp = ExposureManager(state_file=self.state_file)
        status = exp.get_status(is_self=True)

        self.assertIn("gateway", status)
        self.assertIn("exposure", status)
        self.assertIn("security", status)
        self.assertEqual(status["gateway"]["status"], "ONLINE")
        self.assertEqual(status["exposure"]["mode"], "off")
        self.assertEqual(status["security"]["default_mode"], "LOCAL")


class TestPublicSecurityPolicy(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_file = os.path.join(self.temp_dir.name, "perms.json")
        self.policy = PublicSecurityPolicy(policy_file=self.config_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_detect_public_request(self):
        # Local request
        self.assertFalse(self.policy.is_request_public(headers={"host": "127.0.0.1:18010"}, remote_ip="127.0.0.1"))
        self.assertFalse(self.policy.is_request_public(headers={"host": "localhost:18010"}, remote_ip="127.0.0.1"))

        # Public tunnel request via ngrok host
        self.assertTrue(self.policy.is_request_public(headers={"host": "abc-123.ngrok-free.app"}, remote_ip="127.0.0.1"))
        # Public tunnel request via X-Forwarded-Host
        self.assertTrue(self.policy.is_request_public(headers={"x-forwarded-host": "xyz.ngrok.io"}, remote_ip="127.0.0.1"))
        # External remote IP
        self.assertTrue(self.policy.is_request_public(headers={}, remote_ip="203.0.113.195"))

    def test_tool_categorization(self):
        self.assertEqual(self.policy.categorize_tool("fetch_url"), CapabilityGroup.FETCHER)
        self.assertEqual(self.policy.categorize_tool("browser_navigate"), CapabilityGroup.BROWSER)
        self.assertEqual(self.policy.categorize_tool("computer_click"), CapabilityGroup.COMPUTER)
        self.assertEqual(self.policy.categorize_tool("terminal_run"), CapabilityGroup.TERMINAL)
        self.assertEqual(self.policy.categorize_tool("session_export"), CapabilityGroup.SESSIONS)

    def test_default_permissions_filter(self):
        # Fetcher & Browser allowed on public
        self.assertTrue(self.policy.is_tool_allowed_for_public("fetch_url"))
        self.assertTrue(self.policy.is_tool_allowed_for_public("browser_click"))

        # Sensitive host control blocked on public by default
        self.assertFalse(self.policy.is_tool_allowed_for_public("computer_click"))
        self.assertFalse(self.policy.is_tool_allowed_for_public("terminal_run"))
        self.assertFalse(self.policy.is_tool_allowed_for_public("session_import"))

    def test_filter_tools_for_caller(self):
        tools = [
            {"name": "fetch_url", "description": "Fetch web pages"},
            {"name": "browser_navigate", "description": "Navigate"},
            {"name": "computer_type", "description": "Type text"},
            {"name": "session_list", "description": "List sessions"},
        ]

        # Public caller sees only browser & fetcher
        public_tools = self.policy.filter_tools_for_caller(tools, is_public=True)
        public_names = [t["name"] for t in public_tools]
        self.assertIn("fetch_url", public_names)
        self.assertIn("browser_navigate", public_names)
        self.assertNotIn("computer_type", public_names)
        self.assertNotIn("session_list", public_names)

        # Local caller sees everything
        local_tools = self.policy.filter_tools_for_caller(tools, is_public=False)
        self.assertEqual(len(local_tools), 4)


if __name__ == "__main__":
    unittest.main()
