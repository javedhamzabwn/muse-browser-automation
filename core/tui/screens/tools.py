"""core/tui/screens/tools.py — Interactive Tool Registry & Discovery Screen for Muse TUI."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, DataTable, Input, Label, RichLog, Select, Static

from core.exposure.security import PublicSecurityPolicy
from core.mcp.manager import McpManager
from core.tools.benchmark import ToolBenchmarker
from core.tools.health import ToolHealthChecker
from core.tools.installer import ToolInstaller
from core.tools.manifest import ToolCategory, ToolManifest, ToolStatus
from core.tools.registry import ToolRegistry
from core.tui.modals.tool_detail import ToolDetailModal


class ToolsScreen(Widget):
    """Interactive tool registry browser with filtering, searching, and schema inspection."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.registry = ToolRegistry()
        self.mcp_mgr = McpManager()
        self.policy = PublicSecurityPolicy()
        self.all_tools: List[Dict[str, Any]] = []
        self.filtered_tools: List[Dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Tool Registry & Dynamic MCP Capabilities", classes="stat-card-title")

            # Toolbar 1: Search & Filter
            with Horizontal(classes="toolbar"):
                yield Input(placeholder="Search tools...", id="input-tool-search")
                yield Select(
                    [("All Categories", "all"), ("Browser", "browser"), ("Fetcher", "fetcher"),
                     ("Computer Control", "computer_control"), ("Session Vault", "session_vault"),
                     ("Terminal", "terminal"), ("System", "system_inspect")],
                    value="all",
                    id="select-category"
                )
                yield Button("Inspect Details", variant="primary", id="btn-inspect-tool")
                yield Button("Refresh", variant="default", id="btn-refresh-tools")

            # Toolbar 2: Tool Operations
            with Horizontal(classes="toolbar"):
                yield Button("Install Selected", variant="primary", id="btn-install-tool")
                yield Button("Install All", variant="warning", id="btn-install-all")
                yield Button("Update", variant="default", id="btn-update-tool")
                yield Button("Test Health", variant="default", id="btn-test-tool")
                yield Button("Benchmark", variant="default", id="btn-bench-tool")
                yield Button("Toggle Public Access", variant="default", id="btn-toggle-public")
                yield Button("Uninstall", variant="error", id="btn-remove-tool")

            # Tools DataTable
            yield DataTable(id="table-tools", cursor_type="row")

            # Output Log
            with Container(classes="stat-card", id="card-tool-output"):
                yield Label("Operation Output Log", classes="stat-card-title")
                yield RichLog(id="log-tool-output", max_lines=300, highlight=True, markup=True)

    def on_mount(self) -> None:
        table = self.query_one("#table-tools", DataTable)
        table.add_columns("Tool Name", "Category", "Backend", "Status", "Public Access")
        self.reload_tools()

    def reload_tools(self) -> None:
        """Fetches dynamic tools from MCP gateway / tools/list, falling back to ToolRegistry."""
        dynamic_tools = self.mcp_mgr.get_registered_tools()
        if dynamic_tools:
            self.all_tools = dynamic_tools
        else:
            # Fallback to local registry
            self.registry.detect_all()
            self.all_tools = [
                {
                    "name": t.name,
                    "description": t.description,
                    "backend": t.display_name,
                    "inputSchema": {},
                }
                for t in self.registry.list_tools()
            ]
        self.apply_filters()

    def apply_filters(self) -> None:
        query = self.query_one("#input-tool-search", Input).value.strip().lower()
        cat = self.query_one("#select-category", Select).value or "all"

        self.filtered_tools = []
        for t in self.all_tools:
            name = t.get("name", "")
            desc = t.get("description", "")
            tool_cat = self.policy.categorize_tool(name)

            if query and (query not in name.lower() and query not in desc.lower()):
                continue

            if cat != "all" and tool_cat != cat:
                continue

            self.filtered_tools.append(t)

        self.render_table()

    def render_table(self) -> None:
        table = self.query_one("#table-tools", DataTable)
        table.clear()

        for idx, t in enumerate(self.filtered_tools):
            name = t.get("name", "")
            cat = self.policy.categorize_tool(name).upper()
            backend = t.get("backend", "Built-in / Playwright")
            status = "READY"
            pub_ok = self.policy.is_tool_allowed_for_public(name)
            pub_label = "[bold green]ALLOWED[/bold green]" if pub_ok else "[bold yellow]PROTECTED[/bold yellow]"

            table.add_row(name, cat, backend, f"[bold green]{status}[/bold green]", pub_label, key=str(idx))

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "input-tool-search":
            self.apply_filters()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "select-category":
            self.apply_filters()

    def get_selected_tool(self) -> Optional[Dict[str, Any]]:
        table = self.query_one("#table-tools", DataTable)
        if table.cursor_row is not None and 0 <= table.cursor_row < len(self.filtered_tools):
            return self.filtered_tools[table.cursor_row]
        return None

    def get_selected_manifest(self) -> Optional[ToolManifest]:
        tool = self.get_selected_tool()
        if not tool:
            return None
        name = tool.get("name", "")
        m = self.registry.get_tool(name)
        if not m:
            cat_str = self.policy.categorize_tool(name)
            try:
                cat = ToolCategory(cat_str)
            except Exception:
                cat = ToolCategory.BROWSER
            m = ToolManifest(
                name=name,
                display_name=tool.get("backend", name),
                category=cat,
                description=tool.get("description", ""),
            )
        return m

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        log = self.query_one("#log-tool-output", RichLog)

        if bid == "btn-refresh-tools":
            self.reload_tools()
            log.write("[bold cyan]Tool registry reloaded.[/bold cyan]")
            self.app.notify("Tools refreshed")

        elif bid == "btn-inspect-tool":
            tool = self.get_selected_tool()
            if tool:
                self.app.push_screen(ToolDetailModal(tool))
            else:
                self.app.notify("Select a tool row first.", severity="warning")

        elif bid == "btn-install-tool":
            m = self.get_selected_manifest()
            if not m:
                self.app.notify("Select a tool row first.", severity="warning")
                return
            log.write(f"\n[bold yellow]Starting installation for tool: {m.name}...[/bold yellow]")
            self.action_install_tool(m)

        elif bid == "btn-install-all":
            log.write("\n[bold yellow]Starting batch installation for all supported tools...[/bold yellow]")
            self.action_install_all_tools()

        elif bid == "btn-update-tool":
            m = self.get_selected_manifest()
            if not m:
                self.app.notify("Select a tool row first.", severity="warning")
                return
            log.write(f"\n[bold cyan]Checking update for {m.name}...[/bold cyan]")
            self.action_update_tool(m)

        elif bid == "btn-test-tool":
            m = self.get_selected_manifest()
            if not m:
                self.app.notify("Select a tool row first.", severity="warning")
                return
            log.write(f"\n[bold cyan]Running live health check on {m.name}...[/bold cyan]")
            self.action_test_tool(m)

        elif bid == "btn-bench-tool":
            m = self.get_selected_manifest()
            if not m:
                self.app.notify("Select a tool row first.", severity="warning")
                return
            log.write(f"\n[bold cyan]Running benchmark on {m.name}...[/bold cyan]")
            self.action_benchmark_tool(m)

        elif bid == "btn-toggle-public":
            tool = self.get_selected_tool()
            if not tool:
                self.app.notify("Select a tool row first.", severity="warning")
                return
            name = tool.get("name", "")
            new_allowed = self.policy.toggle_tool_permission(name)
            log.write(f"Public access for tool [bold]{name}[/bold] set to: {'[bold green]ALLOWED[/bold green]' if new_allowed else '[bold yellow]PROTECTED (DENIED)[/bold yellow]'}")
            self.app.notify(f"Tool {name} -> {'ALLOWED' if new_allowed else 'PROTECTED'}")
            self.reload_tools()

        elif bid == "btn-remove-tool":
            m = self.get_selected_manifest()
            if not m:
                self.app.notify("Select a tool row first.", severity="warning")
                return
            ok, msg = ToolInstaller.uninstall_tool(m)
            log.write(f"[bold red]{msg}[/bold red]")
            self.app.notify(msg)
            self.reload_tools()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Double clicking or pressing Enter on a row opens its detail view."""
        tool = self.get_selected_tool()
        if tool:
            self.app.push_screen(ToolDetailModal(tool))

    @work(thread=True)
    def action_install_tool(self, manifest: ToolManifest) -> None:
        log = self.query_one("#log-tool-output", RichLog)
        def progress(msg: str) -> None:
            self.app.call_from_thread(log.write, f"  • {msg}")
        ok, msg = ToolInstaller.install_tool(manifest, progress_cb=progress)
        res_style = "bold green" if ok else "bold red"
        self.app.call_from_thread(log.write, f"[{res_style}]Result: {msg}[/{res_style}]")
        self.app.call_from_thread(self.app.notify, f"{manifest.name}: {'Installed' if ok else 'Install Failed'}")
        self.app.call_from_thread(self.reload_tools)

    @work(thread=True)
    def action_install_all_tools(self) -> None:
        log = self.query_one("#log-tool-output", RichLog)
        def progress(name: str, label: str, ok: bool, msg: str) -> None:
            style = "green" if ok else "yellow"
            self.app.call_from_thread(log.write, f"  [{style}]{name}: {label} - {msg}[/{style}]")
        results = ToolInstaller.install_batch(self.registry.list_tools(), progress_cb=progress)
        self.app.call_from_thread(log.write, "[bold green]Batch tool installation finished.[/bold green]")
        self.app.call_from_thread(self.app.notify, "Batch installation finished")
        self.app.call_from_thread(self.reload_tools)

    @work(thread=True)
    def action_update_tool(self, manifest: ToolManifest) -> None:
        log = self.query_one("#log-tool-output", RichLog)
        ok, msg = ToolInstaller.update_tool(manifest)
        style = "bold green" if ok else "bold red"
        self.app.call_from_thread(log.write, f"[{style}]{msg}[/{style}]")
        self.app.call_from_thread(self.app.notify, msg)
        self.app.call_from_thread(self.reload_tools)

    @work(thread=True)
    def action_test_tool(self, manifest: ToolManifest) -> None:
        import asyncio
        log = self.query_one("#log-tool-output", RichLog)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            status, detail = loop.run_until_complete(ToolHealthChecker.check_tool_health(manifest))
            style = "bold green" if status == ToolStatus.READY else "bold yellow"
            self.app.call_from_thread(log.write, f"[{style}]Health Check: {manifest.name} -> {status.value}: {detail or 'OK'}[/{style}]")
            self.app.call_from_thread(self.app.notify, f"{manifest.name}: {status.value}")
        finally:
            loop.close()

    @work(thread=True)
    def action_benchmark_tool(self, manifest: ToolManifest) -> None:
        import asyncio
        log = self.query_one("#log-tool-output", RichLog)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            harness = ToolBenchmarker()
            if manifest.category == ToolCategory.COMPUTER_CONTROL:
                rep = loop.run_until_complete(harness.benchmark_computer_tool(manifest.name, iterations=2))
            else:
                rep = loop.run_until_complete(harness.benchmark_browser_tool(manifest.name, iterations=2))
            self.app.call_from_thread(log.write, f"[bold green]✓ Benchmark Finished for {manifest.name}: {rep.summary}[/bold green]")
            for k, stat in rep.metrics.items():
                self.app.call_from_thread(log.write, f"    {k}: p50={stat.p50_ms}ms, mean={stat.mean_ms}ms, failures={stat.failure_rate*100:.1f}%")
            self.app.call_from_thread(self.app.notify, f"Benchmark complete: {rep.summary}")
        except Exception as e:
            self.app.call_from_thread(log.write, f"[bold red]Benchmark error: {e}[/bold red]")
        finally:
            loop.close()
