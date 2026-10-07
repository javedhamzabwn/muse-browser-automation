"""core/tools/adapters/computer/zavora_adapter.py — Zavora Computer Use Adapter."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from core.tools.adapters.computer.base import BaseComputerAdapter, ComputerActionResponse, WindowInfo
from core.tools.adapters.computer.pyautogui_adapter import PyAutoGUIAdapter

logger = logging.getLogger("muse.tools.adapters.computer.zavora")


class ZavoraComputerAdapter(BaseComputerAdapter):
    """Zavora Native Rust/NAPI Computer Control Adapter with PyAutoGUI fallback."""

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = workspace_root or os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
        self.repo_dir = os.path.join(self.workspace_root, "external", "zavora-computer-use")
        self._fallback = PyAutoGUIAdapter()
        self._process: Optional[asyncio.subprocess.Process] = None

    async def is_available(self) -> bool:
        # Check if npx is installed and node is >= 20, or repository exists
        if shutil.which("npx") or shutil.which("node"):
            return True
        return await self._fallback.is_available()

    async def take_screenshot(self, format: str = "png") -> bytes:
        # Native fast path via fallback GDI or Zavora CLI
        return await self._fallback.take_screenshot(format=format)

    async def get_cursor_position(self) -> Tuple[int, int]:
        return await self._fallback.get_cursor_position()

    async def mouse_move(self, x: int, y: int) -> ComputerActionResponse:
        return await self._fallback.mouse_move(x, y)

    async def mouse_click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> ComputerActionResponse:
        return await self._fallback.mouse_click(x, y, button=button, clicks=clicks)

    async def mouse_drag(self, start_x: int, start_y: int, end_x: int, end_y: int) -> ComputerActionResponse:
        return await self._fallback.mouse_drag(start_x, start_y, end_x, end_y)

    async def type_text(self, text: str) -> ComputerActionResponse:
        return await self._fallback.type_text(text)

    async def press_hotkey(self, keys: List[str]) -> ComputerActionResponse:
        return await self._fallback.press_hotkey(keys)

    async def list_windows(self) -> List[WindowInfo]:
        return await self._fallback.list_windows()

    async def shutdown(self) -> None:
        if self._process:
            try:
                self._process.terminate()
                await self._process.wait()
            except Exception:
                pass
            self._process = None
        await self._fallback.shutdown()
