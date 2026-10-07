import asyncio
import json
import base64
from typing import Any, Dict, List, Optional, Tuple
from core.tools.adapters.computer.base import BaseComputerAdapter, ComputerActionResponse, WindowInfo

class McpComputerAdapter(BaseComputerAdapter):
    '''Proxy adapter that communicates with external MCP servers over stdio.'''

    def __init__(self, backend_name: str, command: str, args: List[str]):
        self.backend_name = backend_name
        self.command = command
        self.args = args
        self.proc: Optional[asyncio.subprocess.Process] = None
        self._msg_id = 1

    async def _ensure_started(self):
        if self.proc is not None:
            return
        import os
        env = os.environ.copy()
        env['Logging__LogLevel__Default'] = 'Warning'
        env['Logging__LogLevel__Microsoft'] = 'Warning'
        env['Logging__Console__FormatterName'] = 'json'

        self.proc = await asyncio.create_subprocess_exec(
            self.command, *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=10 * 1024 * 1024,
            env=env
        )
        
        init_req = {
            "jsonrpc": "2.0",
            "id": self._msg_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "muse-gateway", "version": "3.0.0"}
            }
        }
        self._msg_id += 1
        self.proc.stdin.write(json.dumps(init_req).encode() + b'\n')
        await self.proc.stdin.drain()
        
        while True:
            line = await self.proc.stdout.readline()
            if not line: raise RuntimeError("MCP server died during initialization")
            try:
                resp = json.loads(line.decode().strip())
                if "id" in resp: break
            except:
                pass

        notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        self.proc.stdin.write(json.dumps(notif).encode() + b'\n')
        await self.proc.stdin.drain()

    async def _call_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        await self._ensure_started()
        req_id = self._msg_id
        self._msg_id += 1
        req = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": args}
        }
        self.proc.stdin.write(json.dumps(req).encode() + b'\n')
        await self.proc.stdin.drain()

        while True:
            line = await self.proc.stdout.readline()
            if not line: raise RuntimeError("MCP server died")
            try:
                resp = json.loads(line.decode().strip())
                if resp.get("id") == req_id:
                    if "error" in resp: raise RuntimeError(resp["error"])
                    return resp["result"]
            except Exception as e:
                if isinstance(e, RuntimeError): raise e
                pass

    async def is_available(self) -> bool:
        import shutil
        return shutil.which(self.command) is not None

    async def take_screenshot(self, format: str = "png") -> bytes:
        if self.backend_name == "pyautogui-mcp":
            res = await self._call_tool("pyautogui_screenshot_encoded", {})
        else:
            res = await self._call_tool("computer_screenshot", {})
            
        content = res.get("content", [])
        for block in content:
            if block.get("type") == "image":
                return base64.b64decode(block.get("data", ""))
            if block.get("type") == "text" and len(block.get("text", "")) > 1000:
                return base64.b64decode(block.get("text", ""))
        return b""

    async def get_cursor_position(self) -> Tuple[int, int]:
        return (0, 0)

    async def mouse_move(self, x: int, y: int) -> ComputerActionResponse:
        if self.backend_name == "pyautogui-mcp":
            await self._call_tool("pyautogui_moveTo", {"x": x, "y": y})
        else:
            await self._call_tool("computer_move", {"x": x, "y": y})
        return ComputerActionResponse(success=True, action="mouse_move", details={"x": x, "y": y})

    async def mouse_click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> ComputerActionResponse:
        if self.backend_name == "pyautogui-mcp":
            await self._call_tool("pyautogui_click", {"x": x, "y": y, "button": button, "clicks": clicks})
        else:
            await self._call_tool("computer_click", {"x": x, "y": y, "button": button, "clicks": clicks})
        return ComputerActionResponse(success=True, action="mouse_click", details={})

    async def mouse_drag(self, start_x: int, start_y: int, end_x: int, end_y: int) -> ComputerActionResponse:
        if self.backend_name == "pyautogui-mcp":
            await self._call_tool("pyautogui_moveTo", {"x": start_x, "y": start_y})
            await self._call_tool("pyautogui_dragTo", {"x": end_x, "y": end_y, "button": "left"})
        else:
            await self._call_tool("computer_drag", {"x": end_x, "y": end_y})
        return ComputerActionResponse(success=True, action="mouse_drag", details={})

    async def type_text(self, text: str) -> ComputerActionResponse:
        if self.backend_name == "pyautogui-mcp":
            await self._call_tool("pyautogui_typewrite", {"message": text})
        else:
            await self._call_tool("computer_type", {"text": text})
        return ComputerActionResponse(success=True, action="type_text", details={})

    async def press_hotkey(self, keys: List[str]) -> ComputerActionResponse:
        if self.backend_name == "pyautogui-mcp":
            # pyautogui-mcp might expect them as positional or a list, we just send keys
            await self._call_tool("pyautogui_hotkey", {"keys": keys})
        else:
            await self._call_tool("computer_hotkey", {"keys": keys})
        return ComputerActionResponse(success=True, action="press_hotkey", details={})

    async def list_windows(self) -> List[WindowInfo]:
        return []

    async def shutdown(self) -> None:
        if self.proc:
            try:
                self.proc.terminate()
            except:
                pass
            self.proc = None
