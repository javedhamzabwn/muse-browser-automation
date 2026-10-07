"""core/tui/app.py — Main Textual TUI Application for Muse Browser Automation 4.0."""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import ContentSwitcher, Footer, Header, Label, Static

from core.exposure.manager import ExposureManager
from core.mcp.manager import McpManager
from core.tui.screens.dashboard import DashboardScreen
from core.tui.screens.exposure import ExposureScreen
from core.tui.screens.mcp import McpScreen
from core.tui.screens.sessions import SessionsScreen
from core.tui.screens.settings import SettingsScreen
from core.tui.screens.terminal import TerminalScreen
from core.tui.screens.tests import TestsScreen
from core.tui.screens.tools import ToolsScreen
from core.tui.screens.validation import ValidationScreen
from core.tui.widgets.nav_sidebar import NavSidebar, ScreenSelected
from core.tui.widgets.status_badge import StatusBadge


class MuseApp(App[None]):
    """Main Textual Application for Muse Browser Automation 4.0."""

    TITLE = "MUSE BROWSER AUTOMATION 4.0"
    SUB_TITLE = "Single-Port Multiplexed Gateway :18010"
    CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "styles", "tui.tcss")

    BINDINGS = [
        Binding("1", "switch_screen('dashboard')", "1 Dashboard", show=True),
        Binding("2", "switch_screen('tools')", "2 Tools", show=True),
        Binding("3", "switch_screen('mcp')", "3 MCP", show=True),
        Binding("4", "switch_screen('exposure')", "4 Exposure", show=True),
        Binding("5", "switch_screen('sessions')", "5 Sessions", show=True),
        Binding("6", "switch_screen('terminal')", "6 Terminal", show=True),
        Binding("7", "switch_screen('validation')", "7 Validation", show=True),
        Binding("8", "switch_screen('tests')", "8 Tests", show=True),
        Binding("9", "switch_screen('settings')", "9 Settings", show=True),
        Binding("ctrl+r", "refresh_status", "Refresh", show=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.exp = ExposureManager()
        self.mcp = McpManager(self.exp)
        self.refresh_interval: int = 3
        self._prev_gw_state: Optional[str] = None
        self._prev_exp_mode: Optional[str] = None
        self._timer = None

    def compose(self) -> ComposeResult:
        # Top Header Bar with Live Gateway & MCP Status Badge
        with Horizontal(id="header-bar"):
            yield Label("MUSE 4.0", id="app-title")
            with Container(id="gateway-badge-container"):
                yield StatusBadge(id="status-badge")

        # Main Layout: Nav Sidebar + Content Switcher
        with Horizontal(id="main-layout"):
            yield NavSidebar(id="nav-sidebar")
            with ContentSwitcher(initial="dashboard", id="content-switcher"):
                yield DashboardScreen(id="dashboard")
                yield ToolsScreen(id="tools")
                yield McpScreen(id="mcp")
                yield ExposureScreen(id="exposure")
                yield SessionsScreen(id="sessions")
                yield TerminalScreen(id="terminal")
                yield ValidationScreen(id="validation")
                yield TestsScreen(id="tests")
                yield SettingsScreen(id="settings")

        yield Footer()

    def on_mount(self) -> None:
        self.refresh_all_status()
        self._timer = self.set_interval(self.refresh_interval, self.refresh_all_status)

    def set_refresh_interval(self, seconds: int) -> None:
        self.refresh_interval = max(1, seconds)
        if self._timer:
            self._timer.stop()
        self._timer = self.set_interval(self.refresh_interval, self.refresh_all_status)

    def action_switch_screen(self, screen_id: str) -> None:
        switcher = self.query_one("#content-switcher", ContentSwitcher)
        switcher.current = screen_id
        sidebar = self.query_one("#nav-sidebar", NavSidebar)
        sidebar.set_active(screen_id)

    def on_screen_selected(self, message: ScreenSelected) -> None:
        self.action_switch_screen(message.screen_id)

    def action_refresh_status(self) -> None:
        self.refresh_all_status()
        self.notify("Refreshed status")

    @work(thread=True)
    def refresh_all_status(self) -> None:
        """Fetches live telemetry and updates active screens without blocking UI."""
        try:
            exp_status = self.exp.get_status()
            mcp_status = self.mcp.get_mcp_status()
        except Exception:
            return

        gw = exp_status.get("gateway", {})
        gw_online = gw.get("status") == "ONLINE"
        port = gw.get("port", 18010)

        ep = exp_status.get("exposure", {})
        exp_mode = ep.get("mode", "off")

        loc_mcp = mcp_status.get("local_mcp", {})
        mcp_online = loc_mcp.get("status") == "ONLINE"
        tools_cnt = loc_mcp.get("tools_count", 0)

        # Notify only on genuine state changes (prevents spamming)
        current_gw_state = "ONLINE" if gw_online else "OFFLINE"
        if self._prev_gw_state is not None and self._prev_gw_state != current_gw_state:
            sev = "information" if gw_online else "error"
            self.call_from_thread(self.notify, f"Gateway is now {current_gw_state}", severity=sev)
        self._prev_gw_state = current_gw_state

        if self._prev_exp_mode is not None and self._prev_exp_mode != exp_mode:
            self.call_from_thread(self.notify, f"Exposure mode updated: {exp_mode.upper()}", severity="information")
        self._prev_exp_mode = exp_mode

        # Dispatch updates to widgets on UI thread
        def update_ui():
            try:
                badge = self.query_one("#status-badge", StatusBadge)
                badge.update_status(gw_online, mcp_online, tools_cnt, exp_mode, port)
            except Exception:
                pass

            try:
                dash = self.query_one("#dashboard", DashboardScreen)
                dash.update_data(exp_status, mcp_status)
            except Exception:
                pass

            try:
                mcp_scr = self.query_one("#mcp", McpScreen)
                mcp_scr.update_data(mcp_status)
            except Exception:
                pass

            try:
                exp_scr = self.query_one("#exposure", ExposureScreen)
                exp_scr.update_data(exp_status)
            except Exception:
                pass

        self.call_from_thread(update_ui)
