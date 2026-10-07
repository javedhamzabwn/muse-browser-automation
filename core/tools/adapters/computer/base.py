"""core/tools/adapters/computer/base.py — Abstract Computer Control Adapter Interface."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    process_name: str
    bounds: Tuple[int, int, int, int]  # left, top, right, bottom


@dataclass
class ComputerActionResponse:
    success: bool
    action: str
    details: Dict[str, Any]
    error: Optional[str] = None


class BaseComputerAdapter(abc.ABC):
    """Common interface for computer-use and desktop automation backends."""

    @abc.abstractmethod
    async def is_available(self) -> bool:
        """Check if backend runtime is installed and operational."""
        pass

    @abc.abstractmethod
    async def take_screenshot(self, format: str = "png") -> bytes:
        """Capture entire screen or primary display as bytes."""
        pass

    @abc.abstractmethod
    async def get_cursor_position(self) -> Tuple[int, int]:
        """Return (x, y) coordinates of mouse cursor."""
        pass

    @abc.abstractmethod
    async def mouse_move(self, x: int, y: int) -> ComputerActionResponse:
        """Move cursor to (x, y)."""
        pass

    @abc.abstractmethod
    async def mouse_click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> ComputerActionResponse:
        """Click at (x, y) with specified button."""
        pass

    @abc.abstractmethod
    async def mouse_drag(self, start_x: int, start_y: int, end_x: int, end_y: int) -> ComputerActionResponse:
        """Drag mouse from start to end coordinates."""
        pass

    @abc.abstractmethod
    async def type_text(self, text: str) -> ComputerActionResponse:
        """Type text string with virtual keyboard input."""
        pass

    @abc.abstractmethod
    async def press_hotkey(self, keys: List[str]) -> ComputerActionResponse:
        """Simulate simultaneous key combinations (e.g. ['ctrl', 'c'])."""
        pass

    @abc.abstractmethod
    async def list_windows(self) -> List[WindowInfo]:
        """Enumerate active desktop windows."""
        pass

    @abc.abstractmethod
    async def shutdown(self) -> None:
        """Clean up process handles and close connection."""
        pass
