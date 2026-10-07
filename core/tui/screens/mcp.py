import json
from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Input, Label, RichLog, Select, Static

from core.exposure.manager import ExposureManager
from core.mcp.client_config import McpConfigGenerator
from core.mcp.manager import McpManager


class McpScreen(Widget):
    """Screen for inspecting, testing, configuring, calling, and sharing the Muse MCP Gateway."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.exp = ExposureManager()
        self.mcp = McpManager(self.exp)
        self.registered_tool_names = ["ping", "fetch_url", "browser_status", "tool_status", "browser_open"]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Model Context Protocol (MCP) Gateway", classes="stat-card-title")

            with Container(classes="grid-2"):
                # Local MCP Card
                with Container(classes="stat-card", id="card-local-mcp"):
                    yield Label("Local MCP Endpoint (Port 18010)", classes="stat-card-title")
                    yield Static("Loading local endpoint details...", id="text-local-mcp")

                # Public MCP Card
                with Container(classes="stat-card", id="card-public-mcp"):
                    yield Label("Public MCP Tunnel (ngrok)", classes="stat-card-title")
                    yield Static("Loading public endpoint details...", id="text-public-mcp")

            # Interactive MCP Tool Execution Card
            with Container(classes="stat-card", id="card-mcp-caller"):
                yield Label("Interactive MCP Tool Execution", classes="stat-card-title")
                with Horizontal(classes="toolbar"):
                    yield Select(
                        [(t, t) for t in self.registered_tool_names],
                        value="ping",
                        id="select-mcp-tool"
                    )
                    yield Input(placeholder='JSON parameters e.g. {"url": "https://example.com"}', id="input-mcp-args")
                    yield Button("Execute MCP Tool", variant="primary", id="btn-call-mcp-tool")

            # Result/Diagnostic Log Card
            with Container(classes="stat-card", id="card-mcp-diag"):
                yield Label("Live Protocol Diagnostics & Tool Call Output", classes="stat-card-title")
                yield RichLog(id="log-mcp-output", max_lines=200, highlight=True, markup=True)

            # Action Buttons Toolbar
            with Horizontal(classes="toolbar"):
                yield Button("Test Local MCP", variant="primary", id="btn-test-local")
                yield Button("Test Public MCP", variant="default", id="btn-test-public")
                yield Button("Copy Claude Config", variant="default", id="btn-copy-claude")
                yield Button("Copy Cursor Config", variant="default", id="btn-copy-cursor")
                yield Button("Save Config to Disk", variant="warning", id="btn-save-config-disk")
                yield Button("Copy Active URL", variant="default", id="btn-copy-url")
                yield Button("Refresh", variant="default", id="btn-refresh-mcp")

    def update_data(self, mcp_status: Dict[str, Any]) -> None:
        loc = mcp_status.get("local_mcp", {})
        pub = mcp_status.get("public_mcp", {})

        loc_online = loc.get("status") == "ONLINE"
        loc_markup = (
            f"Endpoint : [dim]{loc.get('url', self.exp.get_local_mcp_url())}[/dim]\n"
            f"Status   : {'[bold green]● ONLINE[/bold green]' if loc_online else '[bold red]○ OFFLINE[/bold red]'}\n"
            f"Protocol : [bold]JSON-RPC 2.0 (Handshake: {'VALID' if loc.get('protocol_valid') else 'PENDING'})[/bold]\n"
            f"Tools    : [bold cyan]{loc.get('tools_count', 0)} registered tools[/bold cyan]\n"
            f"Latency  : [bold]{loc.get('latency_ms', 0.0):.2f} ms[/bold]"
        )
        try:
            self.query_one("#text-local-mcp", Static).update(loc_markup)
        except Exception:
            pass

        purl = pub.get("url")
        pub_online = pub.get("status") == "ONLINE"
        pub_markup = (
            f"Endpoint : [dim]{purl or 'NOT EXPOSED'}[/dim]\n"
            f"Status   : {'[bold green]● ONLINE[/bold green]' if pub_online else '[dim]○ NOT EXPOSED[/dim]'}\n"
            f"Scope    : [bold yellow]Capability Filtered (Local != Public)[/bold yellow]\n"
            f"Exposed  : [bold cyan]{pub.get('tools_count', 0)} tools allowed[/bold cyan]\n"
            f"Latency  : [bold]{pub.get('latency_ms', 0.0):.2f} ms[/bold]"
        )
        try:
            self.query_one("#text-public-mcp", Static).update(pub_markup)
        except Exception:
            pass

    def on_mount(self) -> None:
        self.populate_tools()

    @work(thread=True)
    def populate_tools(self) -> None:
        try:
            tools = self.mcp.get_registered_tools()
            if tools:
                options = [(t.get("name", ""), t.get("name", "")) for t in tools]
                self.app.call_from_thread(self.query_one("#select-mcp-tool", Select).set_options, options)
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        log = self.query_one("#log-mcp-output", RichLog)

        if bid == "btn-test-local":
            log.write("[bold cyan]Testing Local MCP JSON-RPC protocol...[/bold cyan]")
            res = self.mcp.test_local_mcp()
            if res.get("protocol_valid"):
                log.write(
                    f"[bold green]✓ Local MCP Handshake Succeeded![/bold green]\n"
                    f"  Server Name : {res.get('server_name')}\n"
                    f"  Tools Count : {res.get('tools_count')} registered\n"
                    f"  Latency     : {res.get('latency_ms'):.2f} ms"
                )
                self.app.notify("Local MCP Protocol Verified OK", severity="information")
                self.populate_tools()
            else:
                log.write(f"[bold red]✗ Local MCP Failed: {res.get('error') or res.get('status')}[/bold red]")
                self.app.notify("Local MCP Test Failed", severity="error")

        elif bid == "btn-test-public":
            purl = self.exp.get_public_mcp_url()
            if not purl:
                log.write("[bold yellow]No public ngrok tunnel currently active.[/bold yellow]")
                self.app.notify("Public tunnel offline", severity="warning")
                return

            log.write(f"[bold cyan]Testing Public MCP tunnel at {purl}...[/bold cyan]")
            res = self.mcp.test_public_mcp()
            if res.get("protocol_valid"):
                log.write(
                    f"[bold green]✓ Public MCP Tunnel Verified OK![/bold green]\n"
                    f"  Server       : {res.get('server_name')}\n"
                    f"  Tools Allowed: {res.get('tools_count')}\n"
                    f"  Latency      : {res.get('latency_ms'):.2f} ms"
                )
                self.app.notify("Public MCP Verified OK", severity="information")
            else:
                log.write(f"[bold red]✗ Public MCP Failed: {res.get('error')}[/bold red]")
                self.app.notify("Public MCP Test Failed", severity="error")

        elif bid == "btn-call-mcp-tool":
            tool_sel = self.query_one("#select-mcp-tool", Select).value or "ping"
            raw_args = self.query_one("#input-mcp-args", Input).value.strip()
            args_dict = {}
            if raw_args:
                try:
                    args_dict = json.loads(raw_args)
                except Exception as err:
                    log.write(f"[bold red]Invalid JSON parameters: {err}[/bold red]")
                    self.app.notify("Invalid JSON parameters", severity="error")
                    return
            log.write(f"\n[bold yellow]Invoking MCP tool: {tool_sel} with args: {args_dict}...[/bold yellow]")
            self.action_call_tool(str(tool_sel), args_dict)

        elif bid == "btn-save-config-disk":
            try:
                claude_cfg = self.mcp.generate_config(client="claude")
                with open("claude_desktop_config.json", "w", encoding="utf-8") as f:
                    json.dump(claude_cfg, f, indent=2)

                cursor_cfg = self.mcp.generate_config(client="cursor")
                with open(".cursor_mcp.json", "w", encoding="utf-8") as f:
                    json.dump(cursor_cfg, f, indent=2)

                log.write("[bold green]✓ Exported MCP configs to disk:[/bold green]")
                log.write("  • claude_desktop_config.json")
                log.write("  • .cursor_mcp.json")
                self.app.notify("Exported MCP client configs to disk")
            except Exception as e:
                log.write(f"[bold red]Export failed: {e}[/bold red]")
                self.app.notify("Export failed", severity="error")

        elif bid == "btn-copy-claude":
            ok = self.mcp.copy_to_clipboard(client="claude")
            if ok:
                log.write("[green]Copied Claude Desktop configuration to clipboard.[/green]")
                self.app.notify("Copied Claude Desktop config")
            else:
                self.app.notify("Clipboard copy failed", severity="warning")

        elif bid == "btn-copy-cursor":
            ok = self.mcp.copy_to_clipboard(client="cursor")
            if ok:
                log.write("[green]Copied Cursor IDE configuration to clipboard.[/green]")
                self.app.notify("Copied Cursor IDE config")
            else:
                self.app.notify("Clipboard copy failed", severity="warning")

        elif bid == "btn-copy-url":
            active_url = self.exp.get_active_mcp_url()
            ok = self.mcp.copy_to_clipboard(text=active_url)
            if ok:
                log.write(f"[green]Copied active MCP URL: {active_url}[/green]")
                self.app.notify(f"Copied active MCP URL: {active_url}")
            else:
                self.app.notify("Clipboard copy failed", severity="warning")

        elif bid == "btn-refresh-mcp":
            self.app.refresh_all_status()
            self.populate_tools()
            self.app.notify("Refreshed MCP status")

    @work(thread=True)
    def action_call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> None:
        log = self.query_one("#log-mcp-output", RichLog)
        res = self.mcp.test_tool_call(tool_name, arguments)
        if res.get("success"):
            self.app.call_from_thread(log.write, f"[bold green]✓ Tool '{tool_name}' execution succeeded in {res.get('duration_ms')}ms:[/bold green]")
            res_str = json.dumps(res.get("result", {}), indent=2)
            for line in res_str.splitlines()[:30]:
                self.app.call_from_thread(log.write, f"  {line}")
            self.app.call_from_thread(self.app.notify, f"{tool_name}: Succeeded")
        else:
            err_msg = res.get("error") or res.get("result")
            self.app.call_from_thread(log.write, f"[bold red]✗ Tool '{tool_name}' execution failed in {res.get('duration_ms')}ms: {err_msg}[/bold red]")
            self.app.call_from_thread(self.app.notify, f"{tool_name}: Failed", severity="error")
