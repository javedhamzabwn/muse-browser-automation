"""core/tools/adapters/computer/pyautogui_adapter.py — Native Windows / PyAutoGUI Desktop Adapter."""

from __future__ import annotations

import asyncio
import ctypes
import io
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from core.tools.adapters.computer.base import BaseComputerAdapter, ComputerActionResponse, WindowInfo

logger = logging.getLogger("muse.tools.adapters.computer.pyautogui")


class PyAutoGUIAdapter(BaseComputerAdapter):
    """Native Windows API and PyAutoGUI fallback implementation."""

    def __init__(self):
        self._user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None

    async def is_available(self) -> bool:
        return self._user32 is not None

    async def take_screenshot(self, format: str = "png") -> bytes:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    async def get_cursor_position(self) -> Tuple[int, int]:
        if not self._user32:
            return (0, 0)
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        pt = POINT()
        self._user32.GetCursorPos(ctypes.byref(pt))
        return (int(pt.x), int(pt.y))

    async def mouse_move(self, x: int, y: int) -> ComputerActionResponse:
        if not self._user32:
            return ComputerActionResponse(success=False, action="mouse_move", details={}, error="Windows user32 unavailable")
        self._user32.SetCursorPos(int(x), int(y))
        return ComputerActionResponse(success=True, action="mouse_move", details={"x": x, "y": y})

    async def mouse_click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> ComputerActionResponse:
        if not self._user32:
            return ComputerActionResponse(success=False, action="mouse_click", details={}, error="Windows user32 unavailable")
        
        self._user32.SetCursorPos(int(x), int(y))
        time.sleep(0.01)

        # Windows mouse event flags
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004
        MOUSEEVENTF_RIGHTDOWN = 0x0008
        MOUSEEVENTF_RIGHTUP = 0x0010
        MOUSEEVENTF_MIDDLEDOWN = 0x0020
        MOUSEEVENTF_MIDDLEUP = 0x0040

        down_flag, up_flag = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
        if button.lower() == "right":
            down_flag, up_flag = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
        elif button.lower() == "middle":
            down_flag, up_flag = MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP

        for _ in range(clicks):
            self._user32.mouse_event(down_flag, 0, 0, 0, 0)
            time.sleep(0.01)
            self._user32.mouse_event(up_flag, 0, 0, 0, 0)
            if clicks > 1:
                time.sleep(0.05)

        return ComputerActionResponse(success=True, action="mouse_click", details={"x": x, "y": y, "button": button, "clicks": clicks})

    async def mouse_drag(self, start_x: int, start_y: int, end_x: int, end_y: int) -> ComputerActionResponse:
        await self.mouse_move(start_x, start_y)
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004
        self._user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        await asyncio.sleep(0.05)
        # Interpolate
        steps = 10
        for i in range(1, steps + 1):
            cur_x = int(start_x + (end_x - start_x) * (i / steps))
            cur_y = int(start_y + (end_y - start_y) * (i / steps))
            self._user32.SetCursorPos(cur_x, cur_y)
            await asyncio.sleep(0.01)
        self._user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        return ComputerActionResponse(success=True, action="mouse_drag", details={"start": (start_x, start_y), "end": (end_x, end_y)})

    async def type_text(self, text: str) -> ComputerActionResponse:
        # Simulate typing using SendInput or keybd_event
        for ch in text:
            vk = self._user32.VkKeyScanW(ord(ch))
            if vk != -1:
                shift = (vk >> 8) & 1
                key_code = vk & 0xFF
                if shift:
                    self._user32.keybd_event(0x10, 0, 0, 0) # VK_SHIFT down
                self._user32.keybd_event(key_code, 0, 0, 0)
                self._user32.keybd_event(key_code, 0, 2, 0) # KEYEVENTF_KEYUP = 2
                if shift:
                    self._user32.keybd_event(0x10, 0, 2, 0) # VK_SHIFT up
            time.sleep(0.005)
        return ComputerActionResponse(success=True, action="type_text", details={"length": len(text)})

    async def press_hotkey(self, keys: List[str]) -> ComputerActionResponse:
        key_map = {
            "ctrl": 0x11,
            "alt": 0x12,
            "shift": 0x10,
            "enter": 0x0D,
            "tab": 0x09,
            "escape": 0x1B,
            "backspace": 0x08,
            "delete": 0x2E,
        }
        vk_keys = [key_map.get(k.lower(), ord(k.upper()) if len(k) == 1 else 0) for k in keys]
        for vk in vk_keys:
            if vk:
                self._user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.02)
        for vk in reversed(vk_keys):
            if vk:
                self._user32.keybd_event(vk, 0, 2, 0)
        return ComputerActionResponse(success=True, action="press_hotkey", details={"keys": keys})

    async def list_windows(self) -> List[WindowInfo]:
        if not self._user32:
            return []
        windows: List[WindowInfo] = []

        def enum_handler(hwnd, extra):
            if self._user32.IsWindowVisible(hwnd):
                length = self._user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    self._user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value
                    
                    class RECT(ctypes.Structure):
                        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
                    rect = RECT()
                    self._user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    
                    windows.append(
                        WindowInfo(
                            hwnd=hwnd,
                            title=title,
                            process_name="",
                            bounds=(rect.left, rect.top, rect.right, rect.bottom),
                        )
                    )
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        self._user32.EnumWindows(WNDENUMPROC(enum_handler), 0)
        return windows

    async def shutdown(self) -> None:
        pass
