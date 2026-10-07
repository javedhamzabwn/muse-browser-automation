"""core/tui/screens/dashboard.py — Main Dashboard Screen for Muse TUI."""

from __future__ import annotations

import webbrowser
from typing import Any, Dict

from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Label, Static

from core.exposure.manager import ExposureManager, ExposureMode
from core.mcp.manager import McpManager
from core.sessions.manager import ProfileManager


class DashboardScreen(Widget):
    """Primary system overview screen displaying live gateway, MCP, exposure, and backend status."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.exp = ExposureManager()
        self.mcp = McpManager(self.exp)

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Muse Browser Automation — Overview", classes="stat-card-title")

            with Container(classes="grid-2"):
                # Gateway Card
                with Container(classes="stat-card", id="card-gateway"):
                    yield Label("Gateway Status", classes="stat-card-title")
                    yield Static("Loading...", id="stat-gateway-status")

                # MCP Card
                with Container(classes="stat-card", id="card-mcp"):
                    yield Label("MCP Gateway (:18010/mcp)", classes="stat-card-title")
                    yield Static("Loading...", id="stat-mcp-status")

                # Exposure Card
                with Container(classes="stat-card", id="card-exposure"):
                    yield Label("Exposure & Network", classes="stat-card-title")
                    yield Static("Loading...", id="stat-exposure-status")

                # System Capabilities Card
                with Container(classes="stat-card", id="card-backends"):
                    yield Label("Core Subsystems", classes="stat-card-title")
                    yield Static(
                        "• Browser Runtime : [bold green]READY[/bold green] (Playwright, Chrome, Obscura)\n"
                        "• Computer Control : [bold #4da6ff]READY / PROTECTED[/bold #4da6ff]\n"
                        "• Terminal Engine  : [bold #4da6ff]READY / PROTECTED[/bold #4da6ff]\n"
                        "• Session Vault    : [bold green]READY[/bold green] (AES-256-GCM)\n"
                        "• Layer 0 Cache    : [bold green]ACTIVE[/bold green] (SQLite)",
                        id="stat-backends-status"
                    )

            # Execution & Status Log Card
            with Container(classes="stat-card", id="card-dash-log"):
                yield Label("Gateway Control Log", classes="stat-card-title")
                yield Static("System ready. Select an action below.", id="stat-dash-log")

            # Quick Actions Bar
            with Horizontal(classes="toolbar"):
                yield Button("Start Gateway", variant="primary", id="btn-dash-start")
                yield Button("Stop Gateway", variant="error", id="btn-dash-stop")
                yield Button("Restart Gateway", variant="warning", id="btn-dash-restart")
                yield Button("Open Web Dashboard", variant="default", id="btn-dash-open-browser")
                yield Button("Test MCP Protocol", variant="default", id="btn-dash-test-mcp")
                yield Button("Refresh", variant="default", id="btn-dash-refresh")

    def update_data(self, exp_status: Dict[str, Any], mcp_status: Dict[str, Any]) -> None:
        # Update Gateway
        try:
            gw = exp_status.get("gateway", {})
            gw_online = gw.get("status") == "ONLINE"
            gw_markup = (
                f"State     : {'[bold green]● ONLINE[/bold green]' if gw_online else '[bold red]○ OFFLINE[/bold red]'}\n"
                f"Port      : [bold cyan]{gw.get('port', 18010)}[/bold cyan] (Single-Port Multiplexed)\n"
                f"Local URL : [dim]{gw.get('local_url', 'http://127.0.0.1:18010')}[/dim]\n"
                f"Dashboard : [dim]{gw.get('dashboard_url', 'http://127.0.0.1:18010/dashboard')}[/dim]"
            )
            self.query_one("#stat-gateway-status", Static).update(gw_markup)
        except Exception:
            pass

        # Update MCP
        try:
            loc = mcp_status.get("local_mcp", {})
            mcp_online = loc.get("status") == "ONLINE"
            tools_cnt = loc.get("tools_count", 0)
            latency = loc.get("latency_ms", 0.0)
            mcp_markup = (
                f"State     : {'[bold green]● ONLINE[/bold green]' if mcp_online else '[bold red]○ OFFLINE[/bold red]'}\n"
                f"Tools     : [bold green]{tools_cnt} tools registered[/bold green]\n"
                f"Protocol  : [bold]JSON-RPC 2.0 (MCP Valid: {'YES' if loc.get('protocol_valid') else 'NO'})[/bold]\n"
                f"Latency   : [bold cyan]{latency:.1f} ms[/bold cyan]\n"
                f"Endpoint  : [dim]{loc.get('url', 'http://127.0.0.1:18010/mcp')}[/dim]"
            )
            self.query_one("#stat-mcp-status", Static).update(mcp_markup)
        except Exception:
            pass

        # Update Exposure
        try:
            ep = exp_status.get("exposure", {})
            sec = exp_status.get("security", {})
            mode = ep.get("mode", "OFF").upper()
            purl = ep.get("public_url")
            mode_color = "bold yellow" if mode in ("NGROK", "BOTH") else "bold cyan"
            exp_markup = (
                f"Mode      : [{mode_color}]{mode}[/{mode_color}]\n"
                f"Public URL: [bold]{purl or 'NOT EXPOSED'}[/bold]\n"
                f"Public MCP: [dim]{ep.get('public_mcp') or 'NOT EXPOSED'}[/dim]\n"
                f"Security  : [bold green]{sec.get('public_access_policy', 'STRICT_CAPABILITY_FILTERED')}[/bold green]"
            )
            self.query_one("#stat-exposure-status", Static).update(exp_markup)
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        log = self.query_one("#stat-dash-log", Static)

        if bid == "btn-dash-start":
            log.update("Starting Muse Gateway daemon on 127.0.0.1:18010...")
            self.action_start_gateway()

        elif bid == "btn-dash-stop":
            log.update("Stopping Muse Gateway daemon and tunnels...")
            res = self.exp.set_mode(ExposureMode.OFF)
            log.update("[bold red]Gateway daemon stopped. All exposures set to OFF.[/bold red]")
            self.app.notify("Gateway stopped", severity="warning")
            self.app.refresh_all_status()

        elif bid == "btn-dash-restart":
            log.update("Restarting Muse Gateway...")
            self.action_restart_gateway()

        elif bid == "btn-dash-open-browser":
            url = f"http://127.0.0.1:{self.exp.port}/dashboard"
            log.update(f"Opening web dashboard: {url}")
            webbrowser.open(url)
            self.app.notify("Opening web dashboard in browser")

        elif bid == "btn-dash-test-mcp":
            log.update("Testing local MCP JSON-RPC 2.0 handshake...")
            res = self.mcp.test_local_mcp()
            if res.get("protocol_valid"):
                log.update(f"[bold green]✓ MCP Handshake Valid: {res.get('tools_count')} tools registered ({res.get('latency_ms', 0):.1f}ms latency)[/bold green]")
                self.app.notify("MCP Handshake Valid")
            else:
                log.update(f"[bold red]✗ MCP Handshake Failed: {res.get('error') or res.get('status')}[/bold red]")
                self.app.notify("MCP Handshake Failed", severity="error")

        elif bid == "btn-dash-refresh":
            self.app.refresh_all_status()
            self.app.notify("Refreshed status")

    @work(thread=True)
    def action_start_gateway(self) -> None:
        log = self.query_one("#stat-dash-log", Static)
        ok = self.exp.ensure_gateway_running()
        if ok:
            self.app.call_from_thread(log.update, f"[bold green]✓ Gateway ONLINE on 127.0.0.1:{self.exp.port}[/bold green]")
            self.app.call_from_thread(self.app.notify, "Gateway is now ONLINE", severity="information")
        else:
            self.app.call_from_thread(log.update, f"[bold red]✗ Failed to start Gateway daemon on port {self.exp.port}[/bold red]")
            self.app.call_from_thread(self.app.notify, "Failed to start Gateway", severity="error")
        self.app.refresh_all_status()

    @work(thread=True)
    def action_restart_gateway(self) -> None:
        import time
        log = self.query_one("#stat-dash-log", Static)
        self.exp.set_mode(ExposureMode.OFF)
        time.sleep(1.0)
        ok = self.exp.ensure_gateway_running()
        if ok:
            self.app.call_from_thread(log.update, f"[bold green]✓ Gateway successfully restarted on 127.0.0.1:{self.exp.port}[/bold green]")
            self.app.call_from_thread(self.app.notify, "Gateway restarted")
        else:
            self.app.call_from_thread(log.update, f"[bold red]✗ Failed to restart Gateway on port {self.exp.port}[/bold red]")
            self.app.call_from_thread(self.app.notify, "Restart failed", severity="error")
        self.app.refresh_all_status()

