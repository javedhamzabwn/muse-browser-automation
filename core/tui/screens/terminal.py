"""core/tui/screens/terminal.py — Interactive Local Terminal Screen for Muse TUI."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import List, Optional

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Input, Label, RichLog, Static

from core.exposure.security import PublicSecurityPolicy


class TerminalScreen(Widget):
    """Interactive shell terminal emulator for executing local maintenance, scripts, and commands."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.history: List[str] = []
        self.history_index: int = -1
        self.active_proc: Optional[subprocess.Popen] = None
        self.cwd: str = os.getcwd()
        self.policy = PublicSecurityPolicy()

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(classes="toolbar"):
                yield Label("Local Terminal Emulator", classes="stat-card-title")
                yield Button("Clear Screen", variant="default", id="btn-clear-term")
                yield Button("Kill Process", variant="error", id="btn-kill-term")

            yield RichLog(id="terminal-log", highlight=True, markup=True, wrap=True)

            with Horizontal(id="terminal-input-bar"):
                yield Label("PS >", id="terminal-prompt")
                yield Input(placeholder="Type command and press Enter (e.g. python cli.py status)...", id="input-terminal-cmd")

    def on_mount(self) -> None:
        log = self.query_one("#terminal-log", RichLog)
        shell_name = "PowerShell" if sys.platform == "win32" else "Bash / Zsh"
        log.write(Text(f"Muse Browser Automation 4.0 — Terminal Subsystem [{shell_name}]", style="bold cyan"))
        log.write(Text(f"Directory: {self.cwd}", style="dim"))
        log.write(Text("Security Policy: LOCAL: ALLOWED | PUBLIC TUNNEL: RESTRICTED (DENIED)", style="bold green"))
        log.write(Text("-" * 65, style="dim"))

    @work(thread=True)
    def execute_command(self, cmd_line: str) -> None:
        log = self.query_one("#terminal-log", RichLog)
        cmd_stripped = cmd_line.strip()
        if not cmd_stripped:
            return

        self.app.call_from_thread(log.write, Text(f"\nPS {self.cwd}> {cmd_stripped}", style="bold yellow"))

        # Internal helper built-ins
        if cmd_stripped in ("clear", "cls"):
            self.app.call_from_thread(log.clear)
            return

        if cmd_stripped.startswith("cd "):
            target_dir = cmd_stripped[3:].strip().strip('"').strip("'")
            new_path = os.path.abspath(os.path.join(self.cwd, target_dir))
            if os.path.isdir(new_path):
                self.cwd = new_path
                self.app.call_from_thread(log.write, Text(f"Changed directory to: {self.cwd}", style="green"))
            else:
                self.app.call_from_thread(log.write, Text(f"Directory not found: {target_dir}", style="red"))
            return

        shell_cmd = ["powershell", "-NoProfile", "-Command", cmd_stripped] if sys.platform == "win32" else ["bash", "-c", cmd_stripped]

        try:
            self.active_proc = subprocess.Popen(
                shell_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.cwd,
                bufsize=1,
            )

            if self.active_proc.stdout:
                for line in self.active_proc.stdout:
                    clean_line = line.rstrip("\r\n")
                    self.app.call_from_thread(log.write, clean_line)

            self.active_proc.wait()
            ret = self.active_proc.returncode
            if ret != 0:
                self.app.call_from_thread(log.write, Text(f"[Exited with code {ret}]", style="dim red"))
        except Exception as e:
            self.app.call_from_thread(log.write, Text(f"Execution Error: {e}", style="bold red"))
        finally:
            self.active_proc = None

    def on_input_submitted(self, event: Input.Submitted) -> None:
        cmd = event.value
        event.input.value = ""
        if cmd:
            self.history.append(cmd)
            self.history_index = len(self.history)
            self.execute_command(cmd)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-clear-term":
            log = self.query_one("#terminal-log", RichLog)
            log.clear()
        elif event.button.id == "btn-kill-term":
            if self.active_proc and self.active_proc.poll() is None:
                try:
                    self.active_proc.terminate()
                    self.query_one("#terminal-log", RichLog).write(Text("[Process terminated by user]", style="bold red"))
                    self.app.notify("Process terminated", severity="warning")
                except Exception:
                    pass
