import asyncio
import json
import base64
from typing import Any, Dict, List, Optional, Tuple
from core.tools.adapters.computer.base import BaseComputerAdapter, ComputerActionResponse, WindowInfo

class McpComputerAdapter(BaseComputerAdapter):
    """Proxy adapter that communicates with external MCP servers over stdio."""

    def __init__(self, command: str, args: List[str]):
        self.command = command
        self.args = args
        self.proc: Optional[asyncio.subprocess.Process] = None
        self._msg_id = 1

    async def _ensure_started(self):
        if self.proc is not None:
            return
        self.proc = await asyncio.create_subprocess_exec(
            self.command, *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Send initialize
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
        
        # Read until we get initialize response
        while True:
            line = await self.proc.stdout.readline()
            if not line: raise RuntimeError("MCP server died during initialization")
            try:
                resp = json.loads(line.decode().strip())
                if "id" in resp: break
            except:
                pass

        # Send initialized
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
        res = await self._call_tool("screenshot", {})
        # Zavora/PyAutoGUI usually return base64 inside content block
        content = res.get("content", [])
        for block in content:
            if block.get("type") == "image":
                return base64.b64decode(block.get("data", ""))
        return b""

    async def get_cursor_position(self) -> Tuple[int, int]:
        res = await self._call_tool("mouse_position", {})
        return (0, 0) # Fallback if not supported

    async def mouse_move(self, x: int, y: int) -> ComputerActionResponse:
        await self._call_tool("mouse_move", {"x": x, "y": y})
        return ComputerActionResponse(success=True, action="mouse_move", details={"x": x, "y": y})

    async def mouse_click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> ComputerActionResponse:
        await self._call_tool("mouse_click", {"x": x, "y": y, "button": button, "clicks": clicks})
        return ComputerActionResponse(success=True, action="mouse_click", details={})

    async def type_text(self, text: str) -> ComputerActionResponse:
        await self._call_tool("keyboard_type", {"text": text})
        return ComputerActionResponse(success=True, action="type_text", details={})

    async def press_hotkey(self, keys: List[str]) -> ComputerActionResponse:
        await self._call_tool("keyboard_hotkey", {"keys": keys})
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
