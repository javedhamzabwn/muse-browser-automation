"""core/mcp/manager.py — Dynamic MCP Gateway Inspector, Tester & Configuration Manager."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from core.exposure.manager import ExposureManager
from core.mcp.client_config import McpConfigGenerator

logger = logging.getLogger("muse.mcp.manager")


class McpManager:
    """Manages testing, tool discovery, client configurations, and clipboard sharing for Muse MCP."""

    def __init__(self, exposure_manager: Optional[ExposureManager] = None):
        self.exp = exposure_manager or ExposureManager()

    # -------------------------------------------------------------------------
    # JSON-RPC Communication Primitives
    # -------------------------------------------------------------------------
    @staticmethod
    def _post_jsonrpc(endpoint_url: str, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 6.0) -> Dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000) % 100000,
            "method": method,
            "params": params or {},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "muse-mcp-manager/4.0",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # -------------------------------------------------------------------------
    # Live Protocol Testing (Phase 4 & 5)
    # -------------------------------------------------------------------------
    def test_endpoint(self, endpoint_url: str) -> Dict[str, Any]:
        """
        Actually tests MCP JSON-RPC protocol against target endpoint.
        Does not merely check HTTP 200. Executes initialize and tools/list.
        """
        t0 = time.perf_counter()
        results: Dict[str, Any] = {
            "endpoint": endpoint_url,
            "reachable": False,
            "protocol_valid": False,
            "server_name": None,
            "tools_count": 0,
            "latency_ms": 0.0,
            "error": None,
        }

        try:
            # 1. Initialize Handshake
            init_res = self._post_jsonrpc(endpoint_url, "initialize", {"clientInfo": {"name": "muse-mcp-mgr", "version": "4.0"}})
            results["reachable"] = True
            if init_res.get("jsonrpc") == "2.0" and "result" in init_res:
                results["protocol_valid"] = True
                results["server_name"] = init_res["result"].get("serverInfo", {}).get("name")

            # 2. Tools Enumeration
            list_res = self._post_jsonrpc(endpoint_url, "tools/list", {})
            tools = list_res.get("result", {}).get("tools", [])
            results["tools_count"] = len(tools)
            results["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
            results["status"] = "ONLINE" if results["protocol_valid"] else "INVALID_PROTOCOL"

        except Exception as e:
            results["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
            results["status"] = "OFFLINE"
            results["error"] = str(e)

        return results

    def test_local_mcp(self) -> Dict[str, Any]:
        local_url = self.exp.get_local_mcp_url()
        return self.test_endpoint(local_url)

    def test_public_mcp(self) -> Dict[str, Any]:
        public_url = self.exp.get_public_mcp_url()
        if not public_url:
            return {
                "endpoint": None,
                "status": "NOT_EXPOSED",
                "error": "No public ngrok tunnel currently configured",
            }
        return self.test_endpoint(public_url)

    # -------------------------------------------------------------------------
    # Dynamic Tool Discovery (Phase 3)
    # -------------------------------------------------------------------------
    def get_registered_tools(self, endpoint_url: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Dynamically queries tools/list from live MCP gateway.
        This is the runtime source of truth.
        """
        url = endpoint_url or self.exp.get_active_mcp_url()
        try:
            res = self._post_jsonrpc(url, "tools/list", {})
            return res.get("result", {}).get("tools", [])
        except Exception as e:
            logger.warning("Failed to fetch dynamic MCP tools from %s: %s", url, e)
            return []

    def test_tool_call(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None, endpoint_url: Optional[str] = None) -> Dict[str, Any]:
        """Executes a single MCP tool call over JSON-RPC and measures response."""
        url = endpoint_url or self.exp.get_local_mcp_url()
        t0 = time.perf_counter()
        try:
            res = self._post_jsonrpc(url, "tools/call", {"name": tool_name, "arguments": arguments or {}})
            dur = (time.perf_counter() - t0) * 1000.0
            is_err = "error" in res or res.get("result", {}).get("isError") is True
            return {
                "tool": tool_name,
                "endpoint": url,
                "success": not is_err,
                "duration_ms": round(dur, 2),
                "result": res.get("result", res.get("error")),
            }
        except Exception as e:
            dur = (time.perf_counter() - t0) * 1000.0
            return {
                "tool": tool_name,
                "endpoint": url,
                "success": False,
                "duration_ms": round(dur, 2),
                "error": str(e),
            }

    # -------------------------------------------------------------------------
    # MCP Status (Section 6)
    # -------------------------------------------------------------------------
    def get_mcp_status(self) -> Dict[str, Any]:
        local_test = self.test_local_mcp()
        purl = self.exp.get_public_mcp_url()
        public_test = self.test_public_mcp() if purl else None

        active_url = self.exp.get_active_mcp_url()

        return {
            "gateway": {
                "status": "ONLINE" if local_test.get("status") == "ONLINE" else "OFFLINE",
                "protocol": "JSON-RPC 2.0 (Model Context Protocol)",
                "active_mcp_url": active_url,
            },
            "local_mcp": {
                "url": self.exp.get_local_mcp_url(),
                "status": local_test.get("status"),
                "protocol_valid": local_test.get("protocol_valid", False),
                "tools_count": local_test.get("tools_count", 0),
                "latency_ms": local_test.get("latency_ms", 0.0),
            },
            "public_mcp": {
                "url": purl,
                "status": public_test.get("status") if public_test else "NOT_EXPOSED",
                "protocol_valid": public_test.get("protocol_valid", False) if public_test else False,
                "tools_count": public_test.get("tools_count", 0) if public_test else 0,
                "latency_ms": public_test.get("latency_ms", 0.0) if public_test else 0.0,
            },
        }

    # -------------------------------------------------------------------------
    # Configuration Generator & Clipboard (Phase 8 & 9)
    # -------------------------------------------------------------------------
    def generate_config(self, client: str = "generic", target: str = "active") -> Dict[str, Any]:
        """Generates exact configuration snippet for chosen client and scope."""
        if target == "public":
            url = self.exp.get_public_mcp_url() or self.exp.get_local_mcp_url()
        elif target == "local":
            url = self.exp.get_local_mcp_url()
        else:
            url = self.exp.get_active_mcp_url()

        client_lower = client.lower()
        if "claude" in client_lower:
            return McpConfigGenerator.for_claude_desktop(url)
        elif "cursor" in client_lower:
            return McpConfigGenerator.for_cursor(url)
        else:
            return McpConfigGenerator.for_generic_http(url)

    def copy_to_clipboard(self, text: Optional[str] = None, client: str = "claude") -> bool:
        """Copies text (or generated client config) to the system clipboard using native Windows clip tool or pbcopy."""
        if not text:
            cfg = self.generate_config(client=client)
            text = json.dumps(cfg, indent=2)

        if sys.platform == "win32":
            try:
                proc = subprocess.Popen(["clip"], stdin=subprocess.PIPE, shell=True)
                proc.communicate(text.encode("utf-8"))
                return proc.returncode == 0
            except Exception:
                pass
        elif sys.platform == "darwin":
            try:
                proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                proc.communicate(text.encode("utf-8"))
                return proc.returncode == 0
            except Exception:
                pass
        return False
