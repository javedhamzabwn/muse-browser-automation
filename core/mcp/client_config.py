"""core/mcp/client_config.py — Configuration Generator for Supported MCP Clients."""

from __future__ import annotations

import json
from typing import Any, Dict, Union


class McpConfigGenerator:
    """Generates exact configuration snippets for popular agentic MCP clients."""

    @staticmethod
    def for_generic_http(mcp_url: str) -> Dict[str, Any]:
        """Generic HTTP/SSE configuration."""
        return {
            "mcpServers": {
                "muse": {
                    "url": mcp_url,
                    "transport": "http",
                }
            },
            "endpoint": mcp_url,
            "protocol": "JSON-RPC 2.0",
        }

    @staticmethod
    def for_claude_desktop(mcp_url: str) -> Dict[str, Any]:
        """Claude Desktop claude_desktop_config.json snippet."""
        return {
            "mcpServers": {
                "muse": {
                    "url": mcp_url,
                }
            }
        }

    @staticmethod
    def for_cursor(mcp_url: str) -> Dict[str, Any]:
        """Cursor IDE mcp.json snippet."""
        return {
            "mcpServers": {
                "muse": {
                    "url": mcp_url,
                    "type": "http",
                }
            }
        }

    @staticmethod
    def for_python_agent(mcp_url: str) -> str:
        """Python snippet for direct agent connection."""
        return (
            f"from mcp import ClientSession\n"
            f"# Connect to unified Muse Gateway\n"
            f"MUSE_MCP_URL = '{mcp_url}'\n"
        )

    @classmethod
    def generate_config(
        cls,
        mcp_url: str,
        client: str = "claude",
        as_json_string: bool = False,
    ) -> Union[Dict[str, Any], str]:
        c = client.lower()
        if "cursor" in c:
            cfg = cls.for_cursor(mcp_url)
        elif "generic" in c or "http" in c:
            cfg = cls.for_generic_http(mcp_url)
        else:
            cfg = cls.for_claude_desktop(mcp_url)

        if as_json_string:
            return json.dumps(cfg, indent=2)
        return cfg

    @classmethod
    def generate_shareable_summary(cls, mcp_url: str, is_public: bool = False) -> str:
        scope = "PUBLIC TUNNEL (Restricted capabilities)" if is_public else "LOCAL ACCESS (Full capabilities)"
        cfg_claude = cls.generate_config(mcp_url, client="claude", as_json_string=True)
        return (
            f"============================================================\n"
            f"                    MUSE MCP CONNECTION                     \n"
            f"============================================================\n"
            f"Target MCP URL : {mcp_url}\n"
            f"Network Scope  : {scope}\n"
            f"Transport      : HTTP JSON-RPC 2.0 (Model Context Protocol)\n"
            f"Endpoints      : /mcp (tools/list, tools/call)\n"
            f"------------------------------------------------------------\n"
            f"Claude Desktop Configuration:\n"
            f"{cfg_claude}\n"
            f"============================================================"
        )
