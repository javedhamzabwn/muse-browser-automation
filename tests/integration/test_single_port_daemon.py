"""tests/integration/test_single_port_daemon.py — Integration tests for Single-Port Multiplexed Daemon."""

from __future__ import annotations

import json
import unittest

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from daemon.simpled import create_app


class TestSinglePortDaemon(AioHTTPTestCase):
    async def get_application(self) -> web.Application:
        return create_app()

    @unittest_run_loop
    async def test_health_and_status_endpoints(self):
        # /health
        resp = await self.client.request("GET", "/health")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("single_port"), 18010)
        self.assertIn("components", data)
        self.assertIn("ngrok", data)

        # /status
        resp2 = await self.client.request("GET", "/status")
        self.assertEqual(resp2.status, 200)
        data2 = await resp2.json()
        self.assertTrue(data2.get("ok"))
        self.assertEqual(data2.get("single_port"), 18010)

    @unittest_run_loop
    async def test_dashboard_endpoints(self):
        # /dashboard
        resp = await self.client.request("GET", "/dashboard")
        self.assertEqual(resp.status, 200)
        self.assertIn("text/html", resp.headers.get("Content-Type", ""))
        text = await resp.text()
        self.assertIn("Muse Browser Automation 3.0", text)
        self.assertIn("18010", text)

        # Root /
        resp_root = await self.client.request("GET", "/")
        self.assertEqual(resp_root.status, 200)
        text_root = await resp_root.text()
        self.assertIn("Muse Browser Automation 3.0", text_root)

    @unittest_run_loop
    async def test_mcp_initialize_and_tools_list(self):
        # MCP initialize
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"clientInfo": {"name": "test-client", "version": "1.0"}}
        }
        resp = await self.client.request("POST", "/mcp", json=init_payload)
        self.assertEqual(resp.status, 200)
        res = await resp.json()
        self.assertEqual(res.get("jsonrpc"), "2.0")
        self.assertEqual(res.get("id"), 1)
        self.assertIn("serverInfo", res.get("result", {}))
        self.assertEqual(res["result"]["serverInfo"]["name"], "muse-browser")

        # MCP tools/list
        tools_payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        resp2 = await self.client.request("POST", "/mcp", json=tools_payload)
        self.assertEqual(resp2.status, 200)
        res2 = await resp2.json()
        self.assertIn("tools", res2.get("result", {}))
        tool_names = [t["name"] for t in res2["result"]["tools"]]
        self.assertIn("navigate", tool_names)
        self.assertIn("click", tool_names)
        self.assertIn("browser_model", tool_names)
        self.assertIn("tabs_list", tool_names)
        self.assertIn("fetch_url", tool_names)
        self.assertIn("fetch_extract", tool_names)
        self.assertIn("tool_status", tool_names)
        self.assertIn("tool_health", tool_names)
        self.assertIn("browser_task", tool_names)
        self.assertIn("browser_task_status", tool_names)

    @unittest_run_loop
    async def test_mcp_tools_call_tool_status_and_fetch(self):
        # Call tool_status
        status_payload = {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "tool_status", "arguments": {}}
        }
        resp = await self.client.request("POST", "/mcp", json=status_payload)
        self.assertEqual(resp.status, 200)
        res = await resp.json()
        self.assertEqual(res.get("jsonrpc"), "2.0")
        self.assertIn("content", res.get("result", {}))
        text = res["result"]["content"][0]["text"]
        self.assertIn("http_static", text)

        # Call fetch_url (file:// or mock URL or httpbin)
        fetch_payload = {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {"name": "fetch_url", "arguments": {"url": "https://httpbin.org/get"}}
        }
        resp2 = await self.client.request("POST", "/mcp", json=fetch_payload)
        self.assertEqual(resp2.status, 200)
        res2 = await resp2.json()
        self.assertEqual(res2.get("jsonrpc"), "2.0")
        self.assertIn("content", res2.get("result", {}))

    @unittest_run_loop
    async def test_browser_rest_api_endpoints(self):
        # /api/browser/status
        resp = await self.client.request("GET", "/api/browser/status")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("result", data)
        self.assertIn("playwright", data["result"])

        # /api/browser/workspaces
        resp_ws = await self.client.request("GET", "/api/browser/workspaces")
        self.assertEqual(resp_ws.status, 200)
        data_ws = await resp_ws.json()
        self.assertTrue(data_ws.get("ok"))
        self.assertIn("workspaces", data_ws)

    @unittest_run_loop
    async def test_websocket_upgrade(self):
        ws = await self.client.ws_connect("/ws")
        self.assertFalse(ws.closed)

        # Send test ping
        await ws.send_json({"type": "ping", "data": "hello"})
        msg = await ws.receive_json()
        self.assertEqual(msg.get("type"), "pong")

        await ws.close()
        self.assertTrue(ws.closed)


if __name__ == "__main__":
    unittest.main()
