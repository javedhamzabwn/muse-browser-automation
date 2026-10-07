"""core/backends/obscura_backend.py — Obscura stealth browser backend for Muse 3.0."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import urllib.request
from typing import Any, Dict, List, Optional

import websockets

from core.interfaces import BaseBrowserBackend
from core.types import BrowserBackendType, ElementBounds, PageModel, ResolutionMethod, ResolvedElement

CDP_HOST = "127.0.0.1"
CDP_PORT = 9224

SNAPSHOT_JS = r"""function () {
  try {
    const out = [];
    const sel = 'a, button, input, select, textarea, [role="button"], [role="link"], [role="textbox"], [role="checkbox"], [role="switch"], [onclick], [tabindex]:not([tabindex="-1"])';
    let i = 0;
    for (const el of document.querySelectorAll(sel)) {
      try {
        const r = el.getBoundingClientRect();
        if (!r || r.width < 1 || r.height < 1) continue;
        if (r.bottom < 0 || r.top > window.innerHeight || r.right < 0 || r.left > window.innerWidth) continue;
        if (typeof el.checkVisibility === 'function') {
          if (!el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) continue;
        }
        const name = ((el.textContent || '') + ' ' + (el.value || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.title || '') + ' ' + (el.placeholder || '')).replace(/\s+/g, ' ').trim().slice(0, 140);
        out.push({ ref: 'e' + (i++), tag: el.tagName.toLowerCase(), type: el.type || '', role: el.getAttribute('role') || '', name, x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2), w: Math.round(r.width), h: Math.round(r.height) });
        if (out.length >= 400) break;
      } catch (_) {}
    }
    return { url: location.href, title: document.title, count: out.length, elements: out };
  } catch (e) { return { url: location.href, title: document.title, count: 0, elements: [], error: String(e) }; }
}"""

KEYMAP = {
    "Enter": 13, "Tab": 9, "Escape": 27, "Backspace": 8, "Delete": 46,
    "ArrowLeft": 37, "ArrowUp": 38, "ArrowRight": 39, "ArrowDown": 40,
    "Home": 36, "End": 35, "PageUp": 33, "PageDown": 34,
}


class ObscuraBackend(BaseBrowserBackend):
    """Adapter driving Obscura stealth browser via CDP."""

    def __init__(self, host: str = CDP_HOST, port: int = CDP_PORT):
        self.host = host
        self.port = port
        self._ws: Optional[Any] = None
        self._msg_id = 0
        self._target_id: Optional[str] = None
        self._session_id: Optional[str] = None

    @property
    def backend_type(self) -> BrowserBackendType:
        return BrowserBackendType.OBSCURA

    async def is_available(self) -> bool:
        # Check binary existence or if already listening
        obs_dir = os.environ.get("OBSCURA_DIR") or os.path.join(os.path.expanduser("~"), "obscura")
        exe = os.path.join(obs_dir, "obscura.exe")
        return os.path.isfile(exe) or await self.is_connected()

    async def is_connected(self) -> bool:
        if self._ws is None: return False
        try:
            return getattr(self._ws, 'open', getattr(self._ws, 'closed', False) is False)
        except:
            return True

    async def start(self) -> None:
        if await self.is_connected():
            return
        try:
            req = urllib.request.Request(f"http://{self.host}:{self.port}/json/version")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                data = json.loads(resp.read().decode())
                ws_url = data.get("webSocketDebuggerUrl")
        except Exception as e:
            raise RuntimeError(
                f"Obscura is not serving on {self.host}:{self.port} (Error: {e}). "
                "Start it with python obscura/profiles.py main"
            )
            
        if not ws_url:
            ws_url = f"ws://{self.host}:{self.port}/devtools/browser"
        
        self._ws = await websockets.connect(ws_url)
        res = await self._cdp("Target.createTarget", url="about:blank")
        self._target_id = res["result"]["targetId"]
        attach = await self._cdp("Target.attachToTarget", targetId=self._target_id, flatten=True)
        self._session_id = attach["result"]["sessionId"]
        await self._cdp("Page.enable")
        await self._cdp("Runtime.enable")

    async def stop(self) -> None:
        if self._ws:
            try:
                if self._target_id:
                    await self._cdp("Target.closeTarget", targetId=self._target_id)
            except Exception:
                pass
            await self._ws.close()
            self._ws = None

    async def _cdp(self, method: str, **params) -> Dict[str, Any]:
        if not self._ws:
            raise RuntimeError("Obscura CDP WebSocket not connected")
        self._msg_id += 1
        req = {"id": self._msg_id, "method": method, "params": params}
        if self._session_id:
            req["sessionId"] = self._session_id
        await self._ws.send(json.dumps(req))
        while True:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=30)
            resp = json.loads(raw)
            if resp.get("id") == self._msg_id:
                if "error" in resp:
                    raise RuntimeError(f"CDP error {method}: {resp['error']}")
                return resp

    async def list_tabs(self) -> List[Dict[str, Any]]:
        return [{"tabId": self._target_id or "default", "title": await self.get_title(""), "url": await self.get_url("")}]

    async def create_tab(self, url: str = "about:blank") -> str:
        res = await self._cdp("Target.createTarget", url=url)
        return res["result"]["targetId"]

    async def switch_tab(self, tab_id: str, focus: bool = False) -> None:
        pass

    async def close_tab(self, tab_id: str) -> None:
        if tab_id and tab_id != self._target_id:
            await self._cdp("Target.closeTarget", targetId=tab_id)

    async def navigate(self, tab_id: str, url: str, wait_until: str = "load") -> bool:
        await self._cdp("Page.navigate", url=url)
        # Event wait instead of arbitrary sleep 3s
        await asyncio.sleep(0.5)
        return True

    async def get_title(self, tab_id: str) -> str:
        return str(await self.evaluate(tab_id, "document.title") or "")

    async def get_url(self, tab_id: str) -> str:
        return str(await self.evaluate(tab_id, "location.href") or "")

    async def evaluate(self, tab_id: str, expression: str) -> Any:
        # Wrapped as arrow IIFE for Obscura Rust engine compatibility
        wrapped = f"(async()=>{{{expression}}})()"
        r = await self._cdp("Runtime.evaluate", expression=wrapped, returnByValue=True, awaitPromise=True)
        res = r.get("result", {}).get("result", {})
        if res.get("subtype") == "error":
            raise RuntimeError(f"JS error: {res.get('description')}")
        return res.get("value")

    async def click(self, tab_id: str, x: int, y: int) -> bool:
        await self._cdp("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        await self._cdp("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
        await self._cdp("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1)
        return True

    async def type_text(self, tab_id: str, text: str) -> bool:
        for ch in text:
            await self._cdp("Input.dispatchKeyEvent", type="keyDown", text=ch)
        return True

    async def press_key(self, tab_id: str, key: str) -> bool:
        if len(key) == 1:
            return await self.type_text(tab_id, key)
        code = KEYMAP.get(key)
        if code is None:
            raise ValueError(f"Unknown key: {key}")
        for t in ("keyDown", "keyUp"):
            await self._cdp("Input.dispatchKeyEvent", type=t, windowsVirtualKeyCode=code)
        return True

    async def scroll(self, tab_id: str, delta_x: int = 0, delta_y: int = 400) -> bool:
        try:
            await self.evaluate(tab_id, f"window.scrollBy({delta_x}, {delta_y})")
        except Exception:
            await self._cdp("Input.dispatchMouseEvent", type="mouseWheel", x=0, y=0, deltaX=delta_x, deltaY=delta_y)
        return True

    async def screenshot(self, tab_id: str, full_page: bool = False) -> bytes:
        params: Dict[str, Any] = {"format": "png"}
        if full_page:
            params["captureBeyondViewport"] = True
        r = await self._cdp("Page.captureScreenshot", **params)
        return base64.b64decode(r["result"]["data"])

    async def build_page_model(self, tab_id: str) -> PageModel:
        from core.page_model import PageModeler
        return await PageModeler.build(self, tab_id)

    async def get_cookies(self, tab_id: str) -> List[Dict[str, Any]]:
        r = await self._cdp("Storage.getCookies")
        return r.get("result", {}).get("cookies", [])

    async def set_cookies(self, tab_id: str, cookies: List[Dict[str, Any]]) -> bool:
        for c in cookies:
            await self._cdp("Storage.setCookies", cookies=[c])
        return True
