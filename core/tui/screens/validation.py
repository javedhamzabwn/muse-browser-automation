"""core/tui/screens/validation.py — Real-World 6-Category Validation Suite Screen for Muse TUI."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Label, RichLog, Static

from core.validation.runner import ValidationRunner


class ValidationScreen(Widget):
    """Screen for executing and inspecting the 6-category real-world validation matrix."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.runner = ValidationRunner()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Real-World Validation & Verification Matrix", classes="stat-card-title")

            # 6 Category Status Cards Grid
            with Container(classes="grid-3"):
                with Container(classes="stat-card", id="card-val-synthetic"):
                    yield Label("1. Synthetic Tests", classes="stat-card-title")
                    yield Static("Status: [dim]NOT RUN[/dim]", id="text-val-synthetic")

                with Container(classes="stat-card", id="card-val-local"):
                    yield Label("2. Local Tool Tests", classes="stat-card-title")
                    yield Static("Status: [dim]NOT RUN[/dim]", id="text-val-local")

                with Container(classes="stat-card", id="card-val-website"):
                    yield Label("3. Real Website Tests", classes="stat-card-title")
                    yield Static("Status: [dim]NOT RUN[/dim]", id="text-val-website")

                with Container(classes="stat-card", id="card-val-session"):
                    yield Label("4. Browser Sessions", classes="stat-card-title")
                    yield Static("Status: [dim]NOT RUN[/dim]", id="text-val-session")

                with Container(classes="stat-card", id="card-val-computer"):
                    yield Label("5. Computer-Use", classes="stat-card-title")
                    yield Static("Status: [dim]NOT RUN[/dim]", id="text-val-computer")

                with Container(classes="stat-card", id="card-val-mcp"):
                    yield Label("6. MCP Integration", classes="stat-card-title")
                    yield Static("Status: [dim]NOT RUN[/dim]", id="text-val-mcp")

            # Toolbar Controls
            with Horizontal(classes="toolbar"):
                yield Button("Run Fast Validation", variant="primary", id="btn-val-fast")
                yield Button("Run All 6 Categories", variant="warning", id="btn-val-all")
                yield Button("Clear Log", variant="default", id="btn-val-clear")

            # Streaming Log Output
            yield RichLog(id="val-log", highlight=True, markup=True, wrap=True)

    @work(thread=True)
    def run_validation_suite(self, full: bool = False) -> None:
        log = self.query_one("#val-log", RichLog)
        mode_text = "Full (All 6 Categories)" if full else "Fast (Synthetic, Local, MCP)"
        self.app.call_from_thread(log.write, Text(f"\nStarting Validation Matrix: {mode_text}...", style="bold cyan"))

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # 1. Synthetic
        self.app.call_from_thread(self._update_card, "synthetic", "RUNNING", "dim yellow")
        res1 = loop.run_until_complete(self.runner.run_synthetic_tests())
        stat1 = res1.get("status", "PASS")
        self.app.call_from_thread(self._update_card, "synthetic", stat1, "bold green" if stat1 == "PASS" else "bold red")
        self.app.call_from_thread(log.write, f"• Synthetic: {stat1} ({res1.get('passed', 0)}/{res1.get('total_tests', 0)} passed)")

        # 2. Local
        self.app.call_from_thread(self._update_card, "local", "RUNNING", "dim yellow")
        res2 = loop.run_until_complete(self.runner.run_local_tests())
        stat2 = res2.get("status", "PASS")
        self.app.call_from_thread(self._update_card, "local", stat2, "bold green" if stat2 == "PASS" else "bold yellow")
        self.app.call_from_thread(log.write, f"• Local Tools: {stat2} ({res2.get('passed', 0)}/{res2.get('total_tests', 0)} passed)")

        # 6. MCP
        self.app.call_from_thread(self._update_card, "mcp", "RUNNING", "dim yellow")
        res6 = loop.run_until_complete(self.runner.run_mcp_tests())
        stat6 = res6.get("status", "PASS")
        self.app.call_from_thread(self._update_card, "mcp", stat6, "bold green" if stat6 == "PASS" else "bold red")
        self.app.call_from_thread(log.write, f"• MCP Integration: {stat6} ({res6.get('passed', 0)}/{res6.get('total_tests', 0)} passed)")

        if full:
            # 3. Real Website
            self.app.call_from_thread(self._update_card, "website", "RUNNING", "dim yellow")
            res3 = loop.run_until_complete(self.runner.run_website_tests())
            stat3 = res3.get("status", "PASS")
            self.app.call_from_thread(self._update_card, "website", stat3, "bold green" if stat3 == "PASS" else "bold yellow")
            self.app.call_from_thread(log.write, f"• Real Websites: {stat3} ({res3.get('passed', 0)}/{res3.get('total_tests', 0)} passed)")

            # 4. Session
            self.app.call_from_thread(self._update_card, "session", "RUNNING", "dim yellow")
            res4 = loop.run_until_complete(self.runner.run_session_tests())
            stat4 = res4.get("status", "PASS")
            self.app.call_from_thread(self._update_card, "session", stat4, "bold green" if stat4 == "PASS" else "bold yellow")
            self.app.call_from_thread(log.write, f"• Browser Sessions: {stat4} ({res4.get('passed', 0)}/{res4.get('total_tests', 0)} passed)")

            # 5. Computer
            self.app.call_from_thread(self._update_card, "computer", "RUNNING", "dim yellow")
            res5 = loop.run_until_complete(self.runner.run_computer_tests())
            stat5 = res5.get("status", "PASS")
            self.app.call_from_thread(self._update_card, "computer", stat5, "bold green" if stat5 == "PASS" else "bold yellow")
            self.app.call_from_thread(log.write, f"• Computer Use: {stat5} ({res5.get('passed', 0)}/{res5.get('total_tests', 0)} passed)")

        loop.close()
        self.app.call_from_thread(log.write, Text("\n✓ Validation run complete.", style="bold green"))
        self.app.call_from_thread(self.app.notify, "Validation suite completed", severity="information")

    def _update_card(self, cat_key: str, status_text: str, style_markup: str) -> None:
        try:
            self.query_one(f"#text-val-{cat_key}", Static).update(f"Status: [{style_markup}]{status_text}[/{style_markup}]")
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-val-fast":
            self.run_validation_suite(full=False)
        elif event.button.id == "btn-val-all":
            self.run_validation_suite(full=True)
        elif event.button.id == "btn-val-clear":
            self.query_one("#val-log", RichLog).clear()
