"""core/validation/mcp_validator.py — Model Context Protocol Protocol & Gateway Validator."""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("muse.validation.mcp")


@dataclass
class McpTestResult:
    test_name: str
    target_url: str
    success: bool
    duration_ms: float
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class McpGatewayValidator:
    """Validates real JSON-RPC 2.0 communication over http://127.0.0.1:18010/mcp."""

    def __init__(self, mcp_url: str = "http://127.0.0.1:18010/mcp"):
        self.mcp_url = mcp_url

    def _post(self, payload: Dict[str, Any], timeout: float = 10.0) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.mcp_url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def validate_mcp_gateway(self) -> List[McpTestResult]:
        results: List[McpTestResult] = []

        # 1. Initialize Handshake
        t0 = time.perf_counter()
        try:
            init_req = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"clientInfo": {"name": "muse-validator", "version": "4.0"}},
            }
            res = self._post(init_req)
            dur = (time.perf_counter() - t0) * 1000.0
            server_name = res.get("result", {}).get("serverInfo", {}).get("name")
            results.append(
                McpTestResult(
                    test_name="mcp_initialize",
                    target_url=self.mcp_url,
                    success=res.get("jsonrpc") == "2.0" and bool(server_name),
                    duration_ms=round(dur, 2),
                    details={"server_name": server_name},
                )
            )
        except Exception as e:
            dur = (time.perf_counter() - t0) * 1000.0
            results.append(
                McpTestResult(test_name="mcp_initialize", target_url=self.mcp_url, success=False, duration_ms=round(dur, 2), error=str(e))
            )

        # 2. Tools Enumeration
        t0 = time.perf_counter()
        tool_names = []
        try:
            list_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            res = self._post(list_req)
            dur = (time.perf_counter() - t0) * 1000.0
            tools = res.get("result", {}).get("tools", [])
            tool_names = [t["name"] for t in tools]
            results.append(
                McpTestResult(
                    test_name="mcp_tools_list",
                    target_url=self.mcp_url,
                    success=len(tools) >= 20,
                    duration_ms=round(dur, 2),
                    details={"total_tools": len(tools)},
                )
            )
        except Exception as e:
            dur = (time.perf_counter() - t0) * 1000.0
            results.append(
                McpTestResult(test_name="mcp_tools_list", target_url=self.mcp_url, success=False, duration_ms=round(dur, 2), error=str(e))
            )

        # 3. Live Tool Call (tool_status)
        t0 = time.perf_counter()
        try:
            call_req = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "tool_status", "arguments": {}},
            }
            res = self._post(call_req)
            dur = (time.perf_counter() - t0) * 1000.0
            content = res.get("result", {}).get("content", [{}])[0].get("text", "")
            results.append(
                McpTestResult(
                    test_name="mcp_tool_call_tool_status",
                    target_url=self.mcp_url,
                    success="http_static" in content or "playwright" in content,
                    duration_ms=round(dur, 2),
                    details={"content_length": len(content)},
                )
            )
        except Exception as e:
            dur = (time.perf_counter() - t0) * 1000.0
            results.append(
                McpTestResult(test_name="mcp_tool_call_tool_status", target_url=self.mcp_url, success=False, duration_ms=round(dur, 2), error=str(e))
            )

        # 4. Error Handling (Non-existent tool)
        t0 = time.perf_counter()
        try:
            bad_call = {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "non_existent_tool_xyz", "arguments": {}},
            }
            res = self._post(bad_call)
            dur = (time.perf_counter() - t0) * 1000.0
            is_error = "error" in res or res.get("result", {}).get("isError") is True
            err_details = res.get("error", {}).get("code") or res.get("result", {}).get("content", [{}])[0].get("text")
            results.append(
                McpTestResult(
                    test_name="mcp_error_handling",
                    target_url=self.mcp_url,
                    success=is_error,
                    duration_ms=round(dur, 2),
                    details={"error_info": err_details},
                )
            )
        except Exception as e:
            dur = (time.perf_counter() - t0) * 1000.0
            results.append(
                McpTestResult(test_name="mcp_error_handling", target_url=self.mcp_url, success=False, duration_ms=round(dur, 2), error=str(e))
            )

        return results
