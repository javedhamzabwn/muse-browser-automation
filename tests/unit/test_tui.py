"""tests/unit/test_tui.py — Comprehensive Unit & Pilot Tests for Muse Textual TUI."""

import asyncio
import os
import unittest
from unittest.mock import MagicMock, patch

from core.tui.app import MuseApp
from core.tui.modals.confirm_exposure import ConfirmExposureModal
from core.tui.modals.tool_detail import ToolDetailModal
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


class TestMuseTuiApp(unittest.IsolatedAsyncioTestCase):
    """Headless integration test suite using Textual's test pilot."""

    async def test_app_composition_and_mounting(self):
        app = MuseApp()
        async with app.run_test() as pilot:
            # Verify Header and Status Badge
            self.assertIsNotNone(app.query_one("#app-title"))
            badge = app.query_one("#status-badge", StatusBadge)
            self.assertIsNotNone(badge)

            # Verify Nav Sidebar
            sidebar = app.query_one("#nav-sidebar", NavSidebar)
            self.assertIsNotNone(sidebar)

            # Verify all 9 screens are registered inside ContentSwitcher
            switcher = app.query_one("#content-switcher")
            self.assertEqual(switcher.current, "dashboard")

            screens = ["dashboard", "tools", "mcp", "exposure", "sessions", "terminal", "validation", "tests", "settings"]
            for s in screens:
                self.assertIsNotNone(app.query_one(f"#{s}"))

    async def test_keyboard_navigation(self):
        app = MuseApp()
        async with app.run_test() as pilot:
            switcher = app.query_one("#content-switcher")

            # Press keys 1 through 9
            key_screen_map = [
                ("2", "tools"),
                ("3", "mcp"),
                ("4", "exposure"),
                ("5", "sessions"),
                ("6", "terminal"),
                ("7", "validation"),
                ("8", "tests"),
                ("9", "settings"),
                ("1", "dashboard"),
            ]
            for key, expected_screen in key_screen_map:
                await pilot.press(key)
                self.assertEqual(switcher.current, expected_screen)

    async def test_mouse_sidebar_navigation(self):
        app = MuseApp()
        async with app.run_test() as pilot:
            switcher = app.query_one("#content-switcher")
            sidebar = app.query_one("#nav-sidebar", NavSidebar)

            # Click Tools nav button
            await pilot.click("#nav-tools")
            self.assertEqual(switcher.current, "tools")
            self.assertEqual(sidebar.active_id, "tools")

            # Click Exposure nav button
            await pilot.click("#nav-exposure")
            self.assertEqual(switcher.current, "exposure")
            self.assertEqual(sidebar.active_id, "exposure")

            # Click MCP nav button
            await pilot.click("#nav-mcp")
            self.assertEqual(switcher.current, "mcp")
            self.assertEqual(sidebar.active_id, "mcp")

    async def test_dashboard_status_updates(self):
        app = MuseApp()
        async with app.run_test() as pilot:
            dash = app.query_one("#dashboard", DashboardScreen)
            badge = app.query_one("#status-badge", StatusBadge)

            mock_exp_status = {
                "gateway": {
                    "status": "ONLINE",
                    "port": 18010,
                    "local_url": "http://127.0.0.1:18010",
                    "local_mcp": "http://127.0.0.1:18010/mcp",
                    "dashboard_url": "http://127.0.0.1:18010/dashboard",
                },
                "exposure": {
                    "mode": "local",
                    "public_url": None,
                    "public_mcp": None,
                    "started_at": "2026-10-03 12:00:00",
                },
                "security": {
                    "public_access_policy": "STRICT_CAPABILITY_FILTERED"
                }
            }
            mock_mcp_status = {
                "local_mcp": {
                    "url": "http://127.0.0.1:18010/mcp",
                    "status": "ONLINE",
                    "protocol_valid": True,
                    "tools_count": 42,
                    "latency_ms": 12.5,
                },
                "public_mcp": {
                    "url": None,
                    "status": "NOT_EXPOSED",
                    "protocol_valid": False,
                    "tools_count": 0,
                    "latency_ms": 0.0,
                }
            }

            dash.update_data(mock_exp_status, mock_mcp_status)
            badge.update_status(True, True, 42, "LOCAL", 18010)

            self.assertTrue(badge.gateway_online)
            self.assertTrue(badge.mcp_online)
            self.assertEqual(badge.tools_count, 42)
            self.assertEqual(badge.exposure_mode, "LOCAL")

    async def test_tools_screen_filtering(self):
        app = MuseApp()
        async with app.run_test() as pilot:
            await pilot.press("2")  # Switch to tools
            tools_screen = app.query_one("#tools", ToolsScreen)

            tools_screen.all_tools = [
                {"name": "browser_navigate", "description": "Navigate web", "backend": "playwright"},
                {"name": "fetch_url", "description": "Fetch content", "backend": "urllib"},
                {"name": "computer_click", "description": "Click screen", "backend": "pyautogui"},
            ]
            tools_screen.apply_filters()
            self.assertEqual(len(tools_screen.filtered_tools), 3)

            # Filter by search
            search_input = tools_screen.query_one("#input-tool-search")
            search_input.value = "navigate"
            tools_screen.apply_filters()
            self.assertEqual(len(tools_screen.filtered_tools), 1)
            self.assertEqual(tools_screen.filtered_tools[0]["name"], "browser_navigate")

    async def test_settings_screen_save_and_reset(self):
        app = MuseApp()
        async with app.run_test() as pilot:
            await pilot.press("9")  # Switch to settings
            settings_screen = app.query_one("#settings", SettingsScreen)

            btn = settings_screen.query_one("#btn-save-settings")
            btn.press()
            await pilot.pause()

            status_text = str(settings_screen.query_one("#text-settings-status").render())
            self.assertIn("Settings applied", status_text)

            btn_reset = settings_screen.query_one("#btn-reset-settings")
            btn_reset.press()
            await pilot.pause()

            status_text2 = str(settings_screen.query_one("#text-settings-status").render())
            self.assertIn("Settings reset", status_text2)


class TestTuiModals(unittest.TestCase):
    def test_confirm_exposure_modal_dismiss(self):
        modal = ConfirmExposureModal()
        self.assertIsNotNone(modal)

    def test_tool_detail_modal_instantiation(self):
        tool = {
            "name": "browser_navigate",
            "description": "Navigate browser tab to URL",
            "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}},
        }
        modal = ToolDetailModal(tool)
        self.assertIsNotNone(modal)


if __name__ == "__main__":
    unittest.main()
