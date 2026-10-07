"""core/tui/modals/confirm_exposure.py — Security Warning Modal for Public Exposure."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class ConfirmExposureModal(ModalScreen[bool]):
    """Modal dialog prompting explicit administrator confirmation before public exposure."""

    def compose(self) -> ComposeResult:
        with Container(classes="dialog-box"):
            yield Label("Public Exposure Warning", classes="dialog-title")
            with Vertical(classes="dialog-content"):
                yield Static(
                    "You are about to expose the Muse gateway (:18010) through a public ngrok tunnel.\n\n"
                    "[bold red]SECURITY POLICY (LOCAL ACCESS != PUBLIC ACCESS):[/bold red]\n"
                    "• Browser automation and fetcher tools will be accessible to public callers.\n"
                    "• Sensitive host controls ([bold]computer-control, session vault, terminal[/bold]) are [bold green]DENIED[/bold green] on public endpoints by default.\n\n"
                    "Do you wish to proceed and create the public tunnel?"
                )
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", variant="default", id="btn-cancel")
                yield Button("Continue (Enable Public)", variant="error", id="btn-confirm")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)
