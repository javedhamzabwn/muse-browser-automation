"""core/tui/widgets/status_badge.py — Gateway & MCP Status Badge Widget for Muse TUI."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


class StatusBadge(Widget):
    """Header status badge displaying real-time Gateway and MCP connectivity."""

    DEFAULT_CSS = """
    StatusBadge {
        width: auto;
        height: auto;
        content-align: right middle;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.gateway_online: bool = False
        self.mcp_online: bool = False
        self.tools_count: int = 0
        self.exposure_mode: str = "OFF"
        self.port: int = 18010

    def compose(self) -> ComposeResult:
        yield Static(id="badge-text")

    def on_mount(self) -> None:
        self.update_display()

    def update_status(self, gateway_online: bool, mcp_online: bool, tools_count: int, exposure_mode: str, port: int = 18010) -> None:
        self.gateway_online = gateway_online
        self.mcp_online = mcp_online
        self.tools_count = tools_count
        self.exposure_mode = exposure_mode.upper()
        self.port = port
        self.update_display()

    def update_display(self) -> None:
        try:
            static_widget = self.query_one("#badge-text", Static)
        except Exception:
            return

        text = Text()

        # Gateway
        if self.gateway_online:
            text.append("● Gateway ONLINE ", style="bold green")
            text.append(f"(:{self.port})  ", style="dim cyan")
        else:
            text.append("○ Gateway OFFLINE  ", style="bold red")

        # MCP
        if self.mcp_online:
            text.append("● MCP ", style="bold green")
            text.append(f"({self.tools_count} tools)  ", style="green")
        else:
            text.append("○ MCP OFFLINE  ", style="dim red")

        # Exposure Mode
        mode_style = "bold yellow" if self.exposure_mode in ("NGROK", "BOTH") else "bold cyan"
        text.append(f"[{self.exposure_mode}]", style=mode_style)

        static_widget.update(text)
