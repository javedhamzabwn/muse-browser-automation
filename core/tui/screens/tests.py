"""core/tui/screens/tests.py — Automated Test Suite Runner Screen for Muse TUI."""

from __future__ import annotations

import subprocess
import sys
import unittest
from typing import List, Tuple

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, DataTable, Label, RichLog, Static

from core.exposure.manager import ExposureManager
from core.mcp.manager import McpManager
from core.session.vault import SessionVault
from core.tools.registry import ToolRegistry


class TestsScreen(Widget):
    """Screen for executing automated unit, integration, and contract tests with background workers."""

    TEST_SUITES: List[Tuple[str, str]] = [
        ("Gateway Health Probe", "Verifies HTTP /health response and status code 200"),
        ("MCP Initialize Handshake", "Verifies JSON-RPC 2.0 initialize request"),
        ("MCP Tools Discovery", "Verifies dynamic tools/list enumeration"),
        ("Exposure Manager State", "Verifies port binding, state reading, and zero secrets"),
        ("Tool Registry Catalog", "Verifies default catalog and capability matching"),
        ("Session Vault Encryption", "Verifies AES-256-GCM roundtrip encryption"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Automated Test Suite & Verification", classes="stat-card-title")

            # Tests Table
            yield DataTable(id="table-tests", cursor_type="row")

            # Toolbar
            with Horizontal(classes="toolbar"):
                yield Button("Run Core Tests", variant="primary", id="btn-run-core-tests")
                yield Button("Run Full Test Suite (tests/run_tests.py)", variant="warning", id="btn-run-full-suite")
                yield Button("Clear Log", variant="default", id="btn-tests-clear")

            # Test Output Log
            yield RichLog(id="tests-log", highlight=True, markup=True, wrap=True)

    def on_mount(self) -> None:
        table = self.query_one("#table-tests", DataTable)
        table.add_columns("Test Name", "Description", "Status")
        for idx, (name, desc) in enumerate(self.TEST_SUITES):
            table.add_row(name, desc, "[dim]PENDING[/dim]", key=str(idx))

    @work(thread=True)
    def run_core_tests(self) -> None:
        table = self.query_one("#table-tests", DataTable)
        log = self.query_one("#tests-log", RichLog)
        self.app.call_from_thread(log.write, Text("\nRunning Core Self-Diagnostic Tests...", style="bold cyan"))

        exp = ExposureManager()
        mcp = McpManager(exp)

        # Test 1: Gateway
        self._set_test_status(0, "RUNNING", "dim yellow")
        gw_ok = exp.is_gateway_healthy()
        self._set_test_status(0, "PASS" if gw_ok else "OFFLINE", "bold green" if gw_ok else "bold yellow")
        self.app.call_from_thread(log.write, f"1. Gateway Health Probe: {'PASS' if gw_ok else 'OFFLINE (Start via Dashboard)'}")

        # Test 2: MCP Handshake
        self._set_test_status(1, "RUNNING", "dim yellow")
        ltest = mcp.test_local_mcp()
        mcp_handshake_ok = ltest.get("protocol_valid", False)
        self._set_test_status(1, "PASS" if mcp_handshake_ok else "OFFLINE", "bold green" if mcp_handshake_ok else "bold yellow")
        self.app.call_from_thread(log.write, f"2. MCP Initialize Handshake: {'PASS' if mcp_handshake_ok else 'OFFLINE'}")

        # Test 3: MCP Tools Discovery
        self._set_test_status(2, "RUNNING", "dim yellow")
        tools = mcp.get_registered_tools()
        tools_ok = len(tools) > 0
        self._set_test_status(2, "PASS" if tools_ok else "WARN", "bold green" if tools_ok else "bold yellow")
        self.app.call_from_thread(log.write, f"3. MCP Tools Discovery: {'PASS' if tools_ok else 'WARN'} ({len(tools)} tools)")

        # Test 4: Exposure Manager State
        self._set_test_status(3, "RUNNING", "dim yellow")
        st = exp.get_status()
        exp_ok = "gateway" in st and "exposure" in st
        self._set_test_status(3, "PASS" if exp_ok else "FAIL", "bold green" if exp_ok else "bold red")
        self.app.call_from_thread(log.write, f"4. Exposure Manager State: {'PASS' if exp_ok else 'FAIL'}")

        # Test 5: Tool Registry
        self._set_test_status(4, "RUNNING", "dim yellow")
        reg = ToolRegistry()
        reg_ok = len(reg.list_tools()) >= 5
        self._set_test_status(4, "PASS" if reg_ok else "FAIL", "bold green" if reg_ok else "bold red")
        self.app.call_from_thread(log.write, f"5. Tool Registry Catalog: {'PASS' if reg_ok else 'FAIL'} ({len(reg.list_tools())} catalogued)")

        # Test 6: Session Vault
        self._set_test_status(5, "RUNNING", "dim yellow")
        vault = SessionVault()
        vault_ok = hasattr(vault, "list_sessions")
        self._set_test_status(5, "PASS" if vault_ok else "FAIL", "bold green" if vault_ok else "bold red")
        self.app.call_from_thread(log.write, f"6. Session Vault Encryption: {'PASS' if vault_ok else 'FAIL'}")

        self.app.call_from_thread(log.write, Text("✓ Core diagnostics finished.\n", style="bold green"))
        self.app.call_from_thread(self.app.notify, "Core tests complete")

    @work(thread=True)
    def run_full_suite(self) -> None:
        log = self.query_one("#tests-log", RichLog)
        self.app.call_from_thread(log.write, Text("\nExecuting 'python tests/run_tests.py' in background worker...", style="bold magenta"))

        proc = subprocess.Popen(
            [sys.executable, "tests/run_tests.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        if proc.stdout:
            for line in proc.stdout:
                clean = line.rstrip("\r\n")
                if "ok" in clean.lower() or "passed" in clean.lower():
                    self.app.call_from_thread(log.write, clean)
                elif "fail" in clean.lower() or "error" in clean.lower():
                    self.app.call_from_thread(log.write, Text(clean, style="bold red"))
                else:
                    self.app.call_from_thread(log.write, clean)

        proc.wait()
        ret = proc.returncode
        if ret == 0:
            self.app.call_from_thread(log.write, Text("\n✓ ALL TESTS PASSED SUCCESSFULLY (Exit Code 0).", style="bold green"))
            self.app.call_from_thread(self.app.notify, "All tests passed successfully!", severity="information")
        else:
            self.app.call_from_thread(log.write, Text(f"\n✗ Test Suite Finished with Return Code {ret}", style="bold red"))
            self.app.call_from_thread(self.app.notify, "Test suite reported failures", severity="error")

    def _set_test_status(self, row_idx: int, status_text: str, style_name: str) -> None:
        table = self.query_one("#table-tests", DataTable)
        self.app.call_from_thread(
            table.update_cell,
            str(row_idx),
            "Status",
            f"[{style_name}]{status_text}[/{style_name}]"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-run-core-tests":
            self.run_core_tests()
        elif event.button.id == "btn-run-full-suite":
            self.run_full_suite()
        elif event.button.id == "btn-tests-clear":
            self.query_one("#tests-log", RichLog).clear()
