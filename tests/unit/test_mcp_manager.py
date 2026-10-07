"""tests/unit/test_mcp_manager.py — Unit tests for McpManager and McpConfigGenerator."""

import json
import unittest
from unittest.mock import MagicMock, patch

from core.mcp.client_config import McpConfigGenerator
from core.mcp.manager import McpManager


class TestMcpConfigGenerator(unittest.TestCase):
    def test_for_claude_desktop(self):
        url = "http://127.0.0.1:18010/mcp"
        cfg = McpConfigGenerator.for_claude_desktop(url)
        self.assertIn("mcpServers", cfg)
        self.assertIn("muse", cfg["mcpServers"])
        self.assertEqual(cfg["mcpServers"]["muse"]["url"], url)

    def test_for_cursor(self):
        url = "https://muse-test.ngrok.app/mcp"
        cfg = McpConfigGenerator.for_cursor(url)
        self.assertIn("mcpServers", cfg)
        self.assertIn("muse", cfg["mcpServers"])
        self.assertEqual(cfg["mcpServers"]["muse"]["url"], url)

    def test_for_generic_http(self):
        url = "http://127.0.0.1:18010/mcp"
        cfg = McpConfigGenerator.for_generic_http(url)
        self.assertEqual(cfg["endpoint"], url)
        self.assertEqual(cfg["protocol"], "JSON-RPC 2.0")

    def test_as_json_string(self):
        url = "http://127.0.0.1:18010/mcp"
        json_str = McpConfigGenerator.generate_config(url, client="claude", as_json_string=True)
        data = json.loads(json_str)
        self.assertIn("mcpServers", data)

    def test_generate_shareable_summary(self):
        url = "https://muse-test.ngrok.app/mcp"
        summary = McpConfigGenerator.generate_shareable_summary(url, is_public=True)
        self.assertIn(url, summary)
        self.assertIn("MUSE MCP", summary)
        self.assertIn("Claude Desktop", summary)


class TestMcpManager(unittest.TestCase):
    def setUp(self):
        self.mgr = McpManager()

    def test_offline_endpoint(self):
        # Port 59872 is unused
        res = self.mgr.test_endpoint("http://127.0.0.1:59872/mcp")
        self.assertFalse(res["reachable"])
        self.assertFalse(res["protocol_valid"])
        self.assertEqual(res["status"], "OFFLINE")

    @patch("core.mcp.manager.McpManager._post_jsonrpc")
    def test_successful_protocol_test(self, mock_post):
        # Mock initialize response
        mock_post.side_effect = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "muse-mcp-gateway", "version": "4.0.0"},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "tools": [
                        {"name": "fetch_url", "description": "Fetch web pages"},
                        {"name": "browser_navigate", "description": "Navigate browser"},
                    ]
                },
            },
        ]

        res = self.mgr.test_endpoint("http://127.0.0.1:18010/mcp")
        self.assertTrue(res["reachable"])
        self.assertTrue(res["protocol_valid"])
        self.assertEqual(res["server_name"], "muse-mcp-gateway")
        self.assertEqual(res["tools_count"], 2)
        self.assertEqual(res["status"], "ONLINE")

    @patch("core.mcp.manager.McpManager._post_jsonrpc")
    def test_dynamic_tools_query(self, mock_post):
        mock_post.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {"name": "fetch_url", "description": "Fetch"},
                    {"name": "browser_click", "description": "Click"},
                ]
            },
        }

        tools = self.mgr.get_registered_tools("http://127.0.0.1:18010/mcp")
        self.assertEqual(len(tools), 2)
        self.assertEqual(tools[0]["name"], "fetch_url")

    @patch("subprocess.Popen")
    def test_copy_to_clipboard_mock(self, mock_popen):
        proc_mock = MagicMock()
        proc_mock.communicate.return_value = (b"", b"")
        proc_mock.returncode = 0
        mock_popen.return_value = proc_mock

        ok = self.mgr.copy_to_clipboard(client="claude")
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
