"""core/tui/modals/tool_detail.py — Tool Inspection & Schema Modal."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

from core.exposure.security import PublicSecurityPolicy
from core.mcp.manager import McpManager


class ToolDetailModal(ModalScreen[None]):
    """Modal displaying deep tool inspection details, input schemas, and test invocation."""

    def __init__(self, tool_data: Dict[str, Any], **kwargs) -> None:
        super().__init__(**kwargs)
        self.tool = tool_data
        self.policy = PublicSecurityPolicy()
        self.mcp_mgr = McpManager()

    def compose(self) -> ComposeResult:
        name = self.tool.get("name", "Unknown Tool")
        desc = self.tool.get("description", "No description available.")
        backend = self.tool.get("backend", "Built-in / Playwright")
        cat = self.policy.categorize_tool(name)
        pub_allowed = self.policy.is_tool_allowed_for_public(name)

        schema = self.tool.get("inputSchema", {})
        schema_json = json.dumps(schema, indent=2)

        with Container(classes="dialog-box"):
            yield Label(f"Tool: {name}", classes="dialog-title")
            with Vertical(classes="dialog-content"):
                yield Static(f"[bold cyan]Category:[/bold cyan] {cat.upper()}    [bold cyan]Backend:[/bold cyan] {backend}")
                yield Static(f"[bold cyan]Availability:[/bold cyan] LOCAL: [bold green]ALLOWED[/bold green] | PUBLIC: {'[bold green]ALLOWED[/bold green]' if pub_allowed else '[bold yellow]PROTECTED (DENIED)[/bold yellow]'}")
                yield Static(f"\n[bold]Description:[/bold]\n{desc}\n")
                yield Static("[bold]Input Schema (JSON-RPC 2.0):[/bold]")
                yield Static(Syntax(schema_json, "json", theme="monokai", line_numbers=False))
                yield Static("", id="test-result-text")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Test Tool", variant="primary", id="btn-test-tool")
                yield Button("Close", variant="default", id="btn-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-test-tool":
            name = self.tool.get("name", "")
            res = self.mcp_mgr.test_tool_call(name, {})
            result_widget = self.query_one("#test-result-text", Static)
            if res.get("success"):
                result_widget.update(f"[bold green]✓ Test Succeeded ({res.get('duration_ms')}ms)[/bold green]")
            else:
                err = res.get("error") or str(res.get("result"))
                result_widget.update(f"[bold red]✗ Test Failed: {err[:80]}[/bold red]")
        else:
            self.dismiss(None)
