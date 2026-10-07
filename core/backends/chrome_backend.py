"""core/backends/chrome_backend.py — Personal Chrome extension backend for Muse 3.0."""

from __future__ import annotations

import asyncio
import base64
import json
import urllib.request
from typing import Any, Dict, List, Optional

from core.interfaces import BaseBrowserBackend
from core.types import BrowserBackendType, ElementBounds, PageModel, ResolutionMethod, ResolvedElement


class ChromeBackend(BaseBrowserBackend):
    """Adapter driving personal desktop Chrome via the Muse Browser Control extension bridge."""

    def __init__(self, daemon_url: str = "http://127.0.0.1:18010", auth_token: Optional[str] = None):
        self.daemon_url = daemon_url
        self.auth_token = auth_token

    @property
    def backend_type(self) -> BrowserBackendType:
        return BrowserBackendType.CHROME

    def _call_tool_sync(self, tool: str, args: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Any:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        payload_args = args or {}
        payload_args["backend"] = "csi"  # Force the gateway to route this back to the extension
        
        req = urllib.request.Request(
            f"{self.daemon_url}/tool",
            data=json.dumps({"tool": tool, "args": payload_args}).encode("utf-8"),
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not data.get("ok"):
            raise RuntimeError(data.get("error", f"Tool {tool} failed"))
        return data.get("result")

    async def _call_tool(self, tool: str, args: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Any:
        return await asyncio.to_thread(self._call_tool_sync, tool, args, timeout)

    async def is_available(self) -> bool:
        """Check if simpled daemon is running."""
        # If we are inside the daemon, hitting /health causes infinite recursion.
        # Just return True; connectivity will be verified during actual calls.
        return True

    async def is_connected(self) -> bool:
        """Check if Chrome extension is actively connected to the daemon."""
        # Avoid blocking the event loop and infinite recursion inside daemon.
        return True

    async def start(self) -> None:
        """Verify availability."""
        if not await self.is_available():
            raise RuntimeError(f"Chrome daemon is not running at {self.daemon_url}")

    async def stop(self) -> None:
        """No-op for persistent daemon."""
        pass

    async def list_tabs(self) -> List[Dict[str, Any]]:
        return await self._call_tool("tabs_list") or []

    async def create_tab(self, url: str = "about:blank") -> str:
        res = await self._call_tool("tab_create", {"url": url})
        return str(res.get("tabId"))

    async def switch_tab(self, tab_id: str, focus: bool = False) -> None:
        await self._call_tool("tab_switch", {"tabId": int(tab_id), "focus": focus})

    async def close_tab(self, tab_id: str) -> None:
        await self._call_tool("tab_close", {"tabId": int(tab_id)})

    async def navigate(self, tab_id: str, url: str, wait_until: str = "load") -> bool:
        await self._call_tool("navigate", {"tabId": int(tab_id), "url": url})
        return True

    async def get_title(self, tab_id: str) -> str:
        try:
            res = await self._call_tool("page.title", {"tabId": int(tab_id)})
            return res.get("title", "")
        except Exception:
            return await self.evaluate(tab_id, "document.title") or ""

    async def get_url(self, tab_id: str) -> str:
        try:
            res = await self._call_tool("page.url", {"tabId": int(tab_id)})
            return res.get("url", "")
        except Exception:
            return await self.evaluate(tab_id, "location.href") or ""

    async def evaluate(self, tab_id: str, expression: str) -> Any:
        res = await self._call_tool("evaluate", {"tabId": int(tab_id), "js": expression})
        if isinstance(res, dict) and "value" in res:
            return res["value"]
        return res

    async def click(self, tab_id: str, x: int, y: int) -> bool:
        await self._call_tool("click", {"tabId": int(tab_id), "x": x, "y": y, "verify": False})
        return True

    async def type_text(self, tab_id: str, text: str) -> bool:
        await self._call_tool("type", {"tabId": int(tab_id), "text": text})
        return True

    async def press_key(self, tab_id: str, key: str) -> bool:
        await self._call_tool("press_key", {"tabId": int(tab_id), "key": key})
        return True

    async def scroll(self, tab_id: str, delta_x: int = 0, delta_y: int = 400) -> bool:
        await self._call_tool("scroll", {"tabId": int(tab_id), "deltaX": delta_x, "deltaY": delta_y})
        return True

    async def screenshot(self, tab_id: str, full_page: bool = False) -> bytes:
        res = await self._call_tool("screenshot", {"tabId": int(tab_id)})
        if isinstance(res, dict) and "dataUrl" in res:
            b64 = res["dataUrl"].split(",", 1)[1]
            return base64.b64decode(b64)
        if isinstance(res, dict) and "path" in res:
            with open(res["path"], "rb") as f:
                return f.read()
        raise RuntimeError("Unexpected screenshot response format")

    async def build_page_model(self, tab_id: str) -> PageModel:
        try:
            from core.page_model import PageModeler
            return await PageModeler.build(self, tab_id)
        except Exception:
            pass
        snap = await self._call_tool("snapshot", {"tabId": int(tab_id)})
        url = snap.get("url", "")
        title = snap.get("title", "")
        elements: List[ResolvedElement] = []
        buttons: List[Dict[str, Any]] = []
        inputs: List[Dict[str, Any]] = []
        links: List[Dict[str, Any]] = []

        for e in snap.get("elements", []):
            bounds = ElementBounds(
                x=e.get("x", 0) - (e.get("w", 0) // 2),
                y=e.get("y", 0) - (e.get("h", 0) // 2),
                w=e.get("w", 0),
                h=e.get("h", 0),
            )
            resolved = ResolvedElement(
                ref=e.get("ref", ""),
                tag=e.get("tag", ""),
                role=e.get("role", ""),
                name=e.get("name", ""),
                bounds=bounds,
                selector=f"[ref='{e.get('ref', '')}']",
                method=ResolutionMethod.DETERMINISTIC,
                confidence=1.0,
            )
            elements.append(resolved)
            tag = resolved.tag.lower()
            role = resolved.role.lower()
            if tag == "button" or role == "button":
                buttons.append({"ref": resolved.ref, "name": resolved.name, "tag": tag})
            elif tag in ("input", "textarea", "select") or role in ("textbox", "checkbox", "switch"):
                inputs.append({"ref": resolved.ref, "name": resolved.name, "type": e.get("type", "")})
            elif tag == "a" or role == "link":
                links.append({"ref": resolved.ref, "name": resolved.name})

        return PageModel(
            url=url,
            title=title,
            interactive_elements=elements,
            buttons=buttons,
            inputs=inputs,
            links=links,
            summary=f"{len(elements)} interactive items ({len(buttons)} buttons, {len(inputs)} inputs, {len(links)} links)",
        )

    async def get_cookies(self, tab_id: str) -> List[Dict[str, Any]]:
        res = await self._call_tool("cookies.export_cdp", {"tabId": int(tab_id)})
        if isinstance(res, dict) and "cookies" in res:
            return res["cookies"]
        return []

    async def set_cookies(self, tab_id: str, cookies: List[Dict[str, Any]]) -> bool:
        # Chrome extension does not support writing arbitrary cookie jars directly via CDP Storage
        # Return False to indicate non-supported mutation or best-effort evaluate
        return False
