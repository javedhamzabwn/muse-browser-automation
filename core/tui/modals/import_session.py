"""core/tui/modals/import_session.py — Modal for Importing Browser Sessions into Session Vault."""

from __future__ import annotations

from typing import Any, Dict, Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select


class ImportSessionModal(ModalScreen[Optional[Dict[str, Any]]]):
    """Modal dialog for importing authenticated domain-scoped cookies into the Session Vault."""

    def compose(self) -> ComposeResult:
        browser_options = [("Google Chrome", "chrome"), ("Microsoft Edge", "edge"), ("Mozilla Firefox", "firefox")]
        with Container(classes="dialog-box"):
            yield Label("Import Browser Session", classes="dialog-title")
            with Vertical(classes="dialog-content"):
                yield Label("Source Browser:")
                yield Select(browser_options, value="chrome", id="select-browser")
                yield Label("Profile Name:")
                yield Input(value="Default", id="input-profile")
                yield Label("Target Domains (comma-separated, e.g. github.com, x.com):")
                yield Input(placeholder="e.g. github.com", id="input-domains")
                yield Label("Allowed Tools (comma-separated):")
                yield Input(value="playwright,obscura", id="input-tools")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", variant="default", id="btn-cancel")
                yield Button("Import Session", variant="primary", id="btn-import")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-import":
            browser = self.query_one("#select-browser", Select).value or "chrome"
            profile = self.query_one("#input-profile", Input).value.strip() or "Default"
            domains = self.query_one("#input-domains", Input).value.strip()
            tools = self.query_one("#input-tools", Input).value.strip() or "playwright,obscura"
            self.dismiss({
                "browser": browser,
                "profile": profile,
                "domains": domains,
                "tools": tools,
            })
        else:
            self.dismiss(None)
