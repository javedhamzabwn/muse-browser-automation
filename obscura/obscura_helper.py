"""obscura_helper.py — clean CDP wrapper for the Obscura stealth browser.

Ports the proven pieces of the muse-browser-mcp Chrome extension into
Obscura's world:
  - the extension's SNAPSHOT_JS element-extraction (v1.1.4, return-wrapped
    form that proved reliable after the page.snapshot null saga)
  - the extension's KEYMAP for press_key
  - the 8-step CDP flow (browser endpoint -> createTarget -> attachToTarget
    flatten=True -> Page.enable -> sessionId on EVERY call)

Usage:
    import asyncio
    from obscura_helper import ObscuraPage

    async def main():
        async with ObscuraPage() as page:
            await page.navigate("https://example.com")
            snap = await page.snapshot()
            print(snap["title"], snap["count"])
            await page.screenshot("shot.png")

    asyncio.run(main())

Notes:
  - Expects Obscura already serving on 127.0.0.1:9222 (--stealth).
    This helper never auto-starts the daemon; call is_running() to check.
  - Obscura is NOT Chromium (independent Rust engine): heavy web apps may
    render/behave differently from real Chrome. Snapshots degrade gracefully
    (checkVisibility is feature-detected).
"""

import asyncio
import base64
import json
import urllib.request

import websockets

CDP_HOST = "127.0.0.1"
CDP_PORT = 9222

# Ported verbatim from muse-browser-mcp extension/background.js (v1.1.4).
# Fast on purpose: checkVisibility (native) instead of getComputedStyle per
# element, textContent (no layout) instead of innerText (forces reflow).
SNAPSHOT_JS = r'''function () {
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
}'''

# Ported from the extension's KEYMAP.
KEYMAP = {
    "Enter": 13, "Tab": 9, "Escape": 27, "Backspace": 8, "Delete": 46,
    "ArrowLeft": 37, "ArrowUp": 38, "ArrowRight": 39, "ArrowDown": 40,
    "Home": 36, "End": 35, "PageUp": 33, "PageDown": 34,
}


class ObscuraError(Exception):
    pass


def is_running(timeout=3):
    """True if Obscura's CDP endpoint answers on 127.0.0.1:9222."""
    try:
        urllib.request.urlopen(
            "http://%s:%d/json/version" % (CDP_HOST, CDP_PORT), timeout=timeout
        )
        return True
    except Exception:
        return False


def version_info(timeout=5):
    """ /json/version payload (browser, protocol, user agent)."""
    raw = urllib.request.urlopen(
        "http://%s:%d/json/version" % (CDP_HOST, CDP_PORT), timeout=timeout
    ).read().decode()
    return json.loads(raw)


class ObscuraPage:
    """One Obscura target, driven via CDP. Use as an async context manager."""

    def __init__(self, url="about:blank"):
        self._start_url = url
        self._ws = None
        self._msg_id = 0
        self._target_id = None
        self._session_id = None

    async def __aenter__(self):
        if not is_running():
            raise ObscuraError(
                "Obscura is not serving on %s:%d. Start it first, e.g. "
                'obscura.exe serve --host 127.0.0.1 --port 9222 --stealth '
                '--storage-dir <profile>' % (CDP_HOST, CDP_PORT)
            )
        self._ws = await websockets.connect(
            "ws://%s:%d/devtools/browser" % (CDP_HOST, CDP_PORT)
        )
        r = await self._cdp("Target.createTarget", url=self._start_url)
        self._target_id = r["result"]["targetId"]
        # flatten=True is REQUIRED — without it there is no sessionId and
        # every later call fails with "No page for session".
        r = await self._cdp(
            "Target.attachToTarget", targetId=self._target_id, flatten=True
        )
        self._session_id = r["result"]["sessionId"]
        await self._cdp("Page.enable")
        await self._cdp("Runtime.enable")
        return self

    async def __aexit__(self, *exc):
        try:
            if self._target_id:
                await self._cdp("Target.closeTarget", targetId=self._target_id)
        except Exception:
            pass
        try:
            if self._ws:
                await self._ws.close()
        except Exception:
            pass
        self._ws = None

    async def _cdp(self, method, **params):
        self._msg_id += 1
        req = {"id": self._msg_id, "method": method, "params": params}
        if self._session_id:
            req["sessionId"] = self._session_id
        await self._ws.send(json.dumps(req))
        while True:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=30)
            resp = json.loads(raw)
            if "id" in resp and resp["id"] == self._msg_id:
                if "error" in resp:
                    raise ObscuraError("%s: %s" % (method, resp["error"]))
                return resp

    async def navigate(self, url, wait=3):
        """Navigate and wait a beat for the page to settle."""
        await self._cdp("Page.navigate", url=url)
        await asyncio.sleep(wait)
        return url

    async def evaluate(self, js, await_promise=True):
        """Run JS in the page. Wrapped as an arrow-function IIFE because
        Obscura's engine rejects anonymous `function(){}` statements."""
        wrapped = "(async()=>{%s})()" % js
        r = await self._cdp(
            "Runtime.evaluate",
            expression=wrapped,
            returnByValue=True,
            awaitPromise=await_promise,
        )
        res = r["result"]["result"]
        if res.get("type") == "object" and res.get("subtype") == "error":
            raise ObscuraError("JS error: %s" % res.get("description"))
        return res.get("value")

    async def snapshot(self):
        """Structured element list (ported SNAPSHOT_JS). Never returns null:
        on total failure it returns {count: 0, elements: [], error}."""
        wrapped = "(async()=>{return (%s)()})()" % SNAPSHOT_JS
        r = await self._cdp(
            "Runtime.evaluate",
            expression=wrapped,
            returnByValue=True,
            awaitPromise=True,
        )
        val = r["result"]["result"].get("value")
        if val is None:
            return {"url": "", "title": "", "count": 0, "elements": [],
                    "error": "snapshot evaluated to null"}
        return val

    async def title(self):
        return await self.evaluate("return document.title")

    async def screenshot(self, path=None, full_page=False):
        """PNG bytes; optionally saved to path."""
        params = {"format": "png"}
        if full_page:
            params["captureBeyondViewport"] = True
        r = await self._cdp("Page.captureScreenshot", **params)
        data = base64.b64decode(r["result"]["data"])
        if path:
            with open(path, "wb") as f:
                f.write(data)
        return data

    async def click(self, x, y):
        await self._cdp("Input.dispatchMouseEvent",
                        type="mouseMoved", x=x, y=y)
        await self._cdp("Input.dispatchMouseEvent", type="mousePressed",
                        x=x, y=y, button="left", clickCount=1)
        await self._cdp("Input.dispatchMouseEvent", type="mouseReleased",
                        x=x, y=y, button="left", clickCount=1)
        return {"clicked": {"x": x, "y": y}}

    async def type_text(self, text):
        """Best-effort typing via keyDown text events (Obscura's CDP does not
        document Input.insertText, so we don't rely on it)."""
        for ch in text:
            await self._cdp("Input.dispatchKeyEvent", type="keyDown", text=ch)
        return {"typed": len(text)}

    async def press_key(self, key):
        """Named key (Enter, Tab, Escape, arrows...) or a single character."""
        if len(key) == 1:
            return await self.type_text(key)
        code = KEYMAP.get(key)
        if code is None:
            raise ObscuraError("unknown key: %r" % key)
        for t in ("keyDown", "keyUp"):
            await self._cdp("Input.dispatchKeyEvent", type=t,
                            windowsVirtualKeyCode=code)
        return {"pressed": key}

    async def scroll(self, x=0, y=0, dx=0, dy=300):
        await self._cdp("Input.dispatchMouseEvent",
                        type="mouseWheel", x=x, y=y, deltaX=dx, deltaY=dy)
        return {"scrolled": {"dx": dx, "dy": dy}}

    async def get_cookies(self):
        r = await self._cdp("Storage.getCookies")
        return r["result"]["cookies"]

    async def set_cookies(self, cookies):
        """cookies: list of {name, value, domain, path?, secure?, httpOnly?}."""
        for c in cookies:
            await self._cdp("Storage.setCookies", cookies=[c])
        return {"set": len(cookies)}

    async def clear_cookies(self):
        await self._cdp("Storage.clearCookies")
        return {"cleared": True}


async def quick_shot(url, out_path, wait=4):
    """One-shot: navigate, screenshot, close. Returns the page title."""
    async with ObscuraPage() as page:
        await page.navigate(url, wait=wait)
        title = await page.title()
        await page.screenshot(out_path)
        return title


if __name__ == "__main__":
    async def _demo():
        print("Obscura running:", is_running())
        print("Version:", version_info().get("Browser"))
        async with ObscuraPage() as page:
            await page.navigate("https://example.com", wait=3)
            snap = await page.snapshot()
            print("title:", snap.get("title"), "| elements:", snap.get("count"))
            for el in snap.get("elements", [])[:5]:
                print("  %(ref)s %(tag)s '%(name)s' @(%(x)d,%(y)d)" % el)
            await page.screenshot("obscura_helper_demo.png")
            print("screenshot saved: obscura_helper_demo.png")

    asyncio.run(_demo())
