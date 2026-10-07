"""core/tui/screens/settings.py — Configuration & Runtime Settings Screen for Muse TUI."""

from __future__ import annotations

import os
from typing import Any, Dict

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Select, Static

from core.exposure.manager import ExposureManager
from core.exposure.security import PublicSecurityPolicy


class SettingsScreen(Widget):
    """Screen for configuring runtime intervals, preferred backends, and public security exceptions."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.exp = ExposureManager()
        self.policy = PublicSecurityPolicy()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("System Settings & Configuration", classes="stat-card-title")

            with Container(classes="grid-2"):
                # Runtime Configuration Card
                with Container(classes="stat-card", id="card-runtime-settings"):
                    yield Label("TUI Runtime Configuration", classes="stat-card-title")
                    yield Label("Telemetry Refresh Interval:")
                    yield Select(
                        [("2 Seconds (Fast)", 2), ("3 Seconds (Default)", 3), ("5 Seconds (Balanced)", 5), ("10 Seconds (Low CPU)", 10)],
                        value=3,
                        id="select-refresh-interval"
                    )
                    yield Label("\nPreferred Browser Automation Backend:")
                    yield Select(
                        [("Playwright Chromium", "playwright"), ("Google Chrome CDP", "chrome"),
                         ("Obscura Stealth", "obscura"), ("Camoufox Anti-Detect", "camoufox")],
                        value="playwright",
                        id="select-pref-backend"
                    )

                # Public Access Exceptions Card
                with Container(classes="stat-card", id="card-security-settings"):
                    yield Label("Public Security Exception Overrides", classes="stat-card-title")
                    yield Static(
                        "[bold yellow]WARNING:[/bold yellow] By default, sensitive host controls are blocked on public endpoints.\n"
                    )
                    yield Label("Allow Public Computer Control (Mouse/Keys):")
                    yield Select([("DENIED (Secure Default)", "DENY"), ("ALLOWED (Insecure)", "ALLOW")], value="DENY", id="select-pub-computer")
                    yield Label("\nAllow Public Session Vault Decryption:")
                    yield Select([("DENIED (Secure Default)", "DENY"), ("ALLOWED (Insecure)", "ALLOW")], value="DENY", id="select-pub-session")

            # Gateway Information Card
            with Container(classes="stat-card", id="card-gateway-settings"):
                yield Label("Single-Port Gateway Architecture", classes="stat-card-title")
                yield Static(
                    f"• Gateway Port     : [bold cyan]{self.exp.port}[/bold cyan] (Controlled via MUSE_PORT env var)\n"
                    f"• ngrok API Port   : [bold cyan]4040[/bold cyan] (Local discovery endpoint)\n"
                    f"• Single-Port Rule : All MCP, REST, WebSockets, and Dashboard multiplexed on port {self.exp.port}.\n"
                    f"• State Directory  : [dim]{os.path.abspath('state')}[/dim]"
                )

            # Toolbar
            with Horizontal(classes="toolbar"):
                yield Button("Save & Apply Settings", variant="primary", id="btn-save-settings")
                yield Button("Reset to Defaults", variant="default", id="btn-reset-settings")

            # Status log
            yield Static("", id="text-settings-status")

    def on_mount(self) -> None:
        pol = self.policy.get_policy()
        comp_val = pol.get("computer_control", "DENY")
        sess_val = pol.get("session_vault", "DENY")
        try:
            self.query_one("#select-pub-computer", Select).value = comp_val
            self.query_one("#select-pub-session", Select).value = sess_val
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        status_lbl = self.query_one("#text-settings-status", Static)

        if bid == "btn-save-settings":
            comp_perm = self.query_one("#select-pub-computer", Select).value == "ALLOW"
            sess_perm = self.query_one("#select-pub-session", Select).value == "ALLOW"
            self.policy.set_permission("computer_control", comp_perm)
            self.policy.set_permission("session_vault", sess_perm)

            interval = self.query_one("#select-refresh-interval", Select).value or 3
            if hasattr(self.app, "set_refresh_interval"):
                self.app.set_refresh_interval(interval)

            status_lbl.update("[bold green]✓ Settings applied and persisted to state/public_permissions.json.[/bold green]")
            self.app.notify("Settings saved successfully", severity="information")

        elif bid == "btn-reset-settings":
            self.policy.set_permission("computer_control", False)
            self.policy.set_permission("session_vault", False)
            self.query_one("#select-pub-computer", Select).value = "DENY"
            self.query_one("#select-pub-session", Select).value = "DENY"
            self.query_one("#select-refresh-interval", Select).value = 3
            status_lbl.update("[bold yellow]Settings reset to secure defaults.[/bold yellow]")
            self.app.notify("Settings reset to defaults")
