"""core/tui/screens/exposure.py — Network Exposure & Public Tunnel Controller for Muse TUI."""

from __future__ import annotations

from typing import Any, Dict

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Label, Static

from core.exposure.manager import ExposureManager, ExposureMode
from core.tui.modals.confirm_exposure import ConfirmExposureModal


class ExposureScreen(Widget):
    """Screen for managing single-port gateway exposure modes, ngrok tunnels, and security policies."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.exp = ExposureManager()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Exposure & Network Gateway Manager", classes="stat-card-title")

            with Container(classes="grid-2"):
                # Active State Card
                with Container(classes="stat-card", id="card-active-exposure"):
                    yield Label("Active Mode & Configuration", classes="stat-card-title")
                    yield Static("Loading exposure status...", id="text-exposure-mode")

                # Security Policy Card
                with Container(classes="stat-card", id="card-exposure-policy"):
                    yield Label("Public Security Guardrails", classes="stat-card-title")
                    yield Static(
                        "[bold green]LOCAL ACCESS != PUBLIC ACCESS[/bold green]\n\n"
                        "• [bold green]Browser & Fetcher[/bold green]: Allowed on public tunnels\n"
                        "• [bold red]Computer Control[/bold red]: DENIED on public tunnels\n"
                        "• [bold red]Session Vault[/bold red]: DENIED on public tunnels\n"
                        "• [bold red]Terminal Execution[/bold red]: DENIED on public tunnels\n"
                        "• Policy state persisted in [dim]state/public_permissions.json[/dim]",
                        id="text-exposure-policy"
                    )

            # Output log container
            with Container(classes="stat-card", id="card-exposure-log"):
                yield Label("Operation Status", classes="stat-card-title")
                yield Static("Ready.", id="text-exposure-log")

            # Toolbar Controls
            with Horizontal(classes="toolbar"):
                yield Button("Set Mode: LOCAL", variant="primary", id="btn-mode-local")
                yield Button("Expose via ngrok", variant="warning", id="btn-mode-ngrok")
                yield Button("Set Mode: BOTH", variant="warning", id="btn-mode-both")
                yield Button("Stop Exposure (OFF)", variant="error", id="btn-mode-off")
                yield Button("Refresh", variant="default", id="btn-refresh-exposure")

    def update_data(self, exp_status: Dict[str, Any]) -> None:
        ep = exp_status.get("exposure", {})
        gw = exp_status.get("gateway", {})
        mode = ep.get("mode", "OFF").upper()
        purl = ep.get("public_url")

        mode_style = "bold yellow" if mode in ("NGROK", "BOTH") else "bold cyan"
        markup = (
            f"Gateway Port    : [bold cyan]{gw.get('port', 18010)}[/bold cyan] (Single-Port Multiplexed)\n"
            f"Exposure Mode   : [{mode_style}]{mode}[/{mode_style}]\n"
            f"Local Gateway   : [dim]{gw.get('local_url', 'http://127.0.0.1:18010')}[/dim]\n"
            f"Public ngrok    : [bold]{purl or 'NOT EXPOSED'}[/bold]\n"
            f"Public MCP      : [dim]{ep.get('public_mcp') or 'NOT EXPOSED'}[/dim]\n"
            f"Started At      : [dim]{ep.get('started_at') or 'N/A'}[/dim]"
        )
        try:
            self.query_one("#text-exposure-mode", Static).update(markup)
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        log = self.query_one("#text-exposure-log", Static)

        if bid == "btn-mode-local":
            log.update("Setting exposure mode to LOCAL (127.0.0.1:18010)...")
            res = self.exp.set_mode(ExposureMode.LOCAL)
            if "error" in res:
                log.update(f"[bold red]Failed to set LOCAL mode: {res['error']}[/bold red]")
                self.app.notify("Failed to set LOCAL mode", severity="error")
            else:
                log.update("[bold green]Exposure mode set to LOCAL. Public tunnel stopped.[/bold green]")
                self.app.notify("Mode set to LOCAL")
                self.app.refresh_all_status()

        elif bid in ("btn-mode-ngrok", "btn-mode-both"):
            target_mode = ExposureMode.NGROK if bid == "btn-mode-ngrok" else ExposureMode.BOTH

            def on_confirm(confirmed: bool) -> None:
                if confirmed:
                    log.update(f"Connecting {target_mode.value.upper()} exposure via ngrok...")
                    res = self.exp.set_mode(target_mode)
                    if "error" in res:
                        log.update(f"[bold red]ngrok Exposure Failed: {res['error']}[/bold red]")
                        self.app.notify("Public exposure failed", severity="error")
                    else:
                        log.update(f"[bold green]Public exposure active! Public URL: {res.get('public_url')}[/bold green]")
                        self.app.notify(f"Mode set to {target_mode.value.upper()}", severity="information")
                        self.app.refresh_all_status()
                else:
                    log.update("Public exposure canceled by administrator.")

            self.app.push_screen(ConfirmExposureModal(), on_confirm)

        elif bid == "btn-mode-off":
            log.update("Stopping exposure and gateway...")
            res = self.exp.set_mode(ExposureMode.OFF)
            log.update("[bold yellow]Exposure stopped. Gateway offline.[/bold yellow]")
            self.app.notify("Exposure stopped (OFF)", severity="warning")
            self.app.refresh_all_status()

        elif bid == "btn-refresh-exposure":
            self.app.refresh_all_status()
            self.app.notify("Refreshed exposure status")
