"""core/validation — Real-world validation suite for browser, computer, and MCP subsystems."""

from core.validation.browser_validator import BrowserRealWorldValidator, WebsiteTestResult
from core.validation.computer_validator import ComputerRealWorldValidator, ComputerTestResult
from core.validation.mcp_validator import McpGatewayValidator, McpTestResult
from core.validation.runner import ValidationRunner

__all__ = [
    "BrowserRealWorldValidator",
    "WebsiteTestResult",
    "ComputerRealWorldValidator",
    "ComputerTestResult",
    "McpGatewayValidator",
    "McpTestResult",
    "ValidationRunner",
]
