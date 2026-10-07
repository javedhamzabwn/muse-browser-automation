"""core/tui/widgets/nav_sidebar.py — Left Navigation Sidebar Widget for Muse TUI."""

from __future__ import annotations

from typing import List, Tuple
from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button


class ScreenSelected(Message):
    """Event emitted when a navigation item is selected."""
    def __init__(self, screen_id: str) -> None:
        super().__init__()
        self.screen_id = screen_id


class NavSidebar(Widget):
    """Sidebar containing buttons for the primary screens."""

    NAV_ITEMS: List[Tuple[str, str, str]] = [
        ("dashboard", "1. Dashboard", "dashboard"),
        ("tools", "2. Tools", "tools"),
        ("mcp", "3. MCP", "mcp"),
        ("exposure", "4. Exposure", "exposure"),
        ("sessions", "5. Sessions", "sessions"),
        ("terminal", "6. Terminal", "terminal"),
        ("validation", "7. Validation", "validation"),
        ("tests", "8. Tests", "tests"),
        ("settings", "9. Settings", "settings"),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.active_id: str = "dashboard"

    def compose(self) -> ComposeResult:
        for sid, label, name in self.NAV_ITEMS:
            btn = Button(label, id=f"nav-{sid}", classes="nav-button")
            if sid == self.active_id:
                btn.add_class("-active")
            yield btn

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id.startswith("nav-"):
            sid = btn_id[4:]
            self.set_active(sid)
            if hasattr(self.app, "action_switch_screen"):
                self.app.action_switch_screen(sid)

    def set_active(self, screen_id: str) -> None:
        self.active_id = screen_id
        for sid, _, _ in self.NAV_ITEMS:
            try:
                b = self.query_one(f"#nav-{sid}", Button)
                if sid == screen_id:
                    b.add_class("-active")
                else:
                    b.remove_class("-active")
            except Exception:
                pass
