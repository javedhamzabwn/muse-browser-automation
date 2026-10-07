"""core/mcp — Model Context Protocol Gateway Manager and Compatibility Layer."""

from core.mcp.client_config import McpConfigGenerator
from core.mcp.manager import McpManager

__all__ = [
    "McpManager",
    "McpConfigGenerator",
]
