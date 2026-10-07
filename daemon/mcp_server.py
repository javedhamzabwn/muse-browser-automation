#!/usr/bin/env python3
"""muse-browser MCP server (v1).

stdio MCP (newline-delimited JSON-RPC, like the MCP TS SDK expects) on one
side; WebSocket server on 127.0.0.1:19091 on the other, which the
"Muse Browser Control" Chrome extension connects to. Forwards tool calls to
the extension, which executes them against the user's real Chrome via CDP.

Loopback only. Nothing leaves this PC.
"""
import asyncio
import json
import os
import sys
import time
import urllib.request

import websockets

WS_HOST = "127.0.0.1"
WS_PORT = 19091
DAEMON_HTTP_URL = os.environ.get("MUSE_DAEMON_URL") or "http://127.0.0.1:18010"
AUTH_TOKEN = os.environ.get("MUSE_AUTH_TOKEN", "").strip()

ext_ws = None            # active extension websocket
ext_ready = asyncio.Event()
pending = {}
msg_id = 0
daemon_mode = False


def is_daemon_running():
    try:
        headers = {}
        if AUTH_TOKEN:
            headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
        req = urllib.request.Request(f"{DAEMON_HTTP_URL}/health", headers=headers)
        with urllib.request.urlopen(req, timeout=1) as r:
            data = json.loads(r.read().decode())
            return bool(data.get("ok"))
    except Exception:
        return False


def call_daemon_http(method, params=None, timeout=30):
    payload = json.dumps({"tool": method, "args": params or {}}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    req = urllib.request.Request(f"{DAEMON_HTTP_URL}/tool", data=payload, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        res = json.loads(r.read().decode())
        if not res.get("ok"):
            raise RuntimeError(res.get("error", "daemon error"))
        return res.get("result")


async def ws_handler(websocket):
    global ext_ws
    ext_ws = websocket
    ext_ready.set()
    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            mid = msg.get("id")
            if mid is not None and mid in pending:
                fut = pending.pop(mid)
                if not fut.done():
                    fut.set_result(msg)
    finally:
        if ext_ws is websocket:
            ext_ws = None
            ext_ready.clear()


async def call_ext(method, params=None, timeout=30):
    global msg_id
    if daemon_mode:
        return await asyncio.to_thread(call_daemon_http, method, params, timeout)

    if not ext_ready.is_set():
        try:
            await asyncio.wait_for(ext_ready.wait(), timeout=10)
        except asyncio.TimeoutError:
            raise RuntimeError("extension not connected (is the Muse Browser Control extension installed and enabled?)")
    msg_id += 1
    mid = msg_id
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    pending[mid] = fut
    await ext_ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    try:
        resp = await asyncio.wait_for(fut, timeout=timeout)
    finally:
        pending.pop(mid, None)
    if not resp.get("ok"):
        raise RuntimeError(resp.get("error", "extension error"))
    return resp.get("result")


async def do_snapshot(tabId=None):
    return await call_ext("page.snapshot", {"tabId": tabId} if tabId else {})


# ---------------- MCP tools ----------------
async def tool_click(args):
    x, y = args.get("x"), args.get("y")
    tid = args.get("tabId")
    if x is None and args.get("ref"):
        snap = await do_snapshot(tid)
        match = next((e for e in snap.get("elements", []) if e.get("ref") == args["ref"]), None)
        if not match:
            raise RuntimeError(f"ref {args['ref']} not found in current snapshot")
        x, y = match["x"], match["y"]
    if x is None or y is None:
        raise RuntimeError("click needs x,y or a ref from snapshot")
    verify = args.get("verify", True)
    before = await do_snapshot(tid) if verify else None
    await call_ext("input.click", {"x": x, "y": y, **({"tabId": tid} if tid else {})})
    if not verify:
        return {"clicked": {"x": x, "y": y}}
    # Event-driven wait loop (15ms polling up to 500ms) replacing arbitrary sleep(0.8)
    deadline = time.perf_counter() + 0.5
    changed = False
    after = before or {}
    while time.perf_counter() < deadline:
        await asyncio.sleep(0.015)
        after = await do_snapshot(tid)
        if (
            before.get("url") != after.get("url")
            or before.get("title") != after.get("title")
            or before.get("count") != after.get("count")
        ):
            changed = True
            break
    return {
        "clicked": {"x": x, "y": y},
        "verified": True,
        "page_changed": changed,
        "before": {"url": before.get("url"), "title": before.get("title"), "elements": before.get("count")},
        "after": {"url": after.get("url"), "title": after.get("title"), "elements": after.get("count")},
    }


TID = {"tabId": {"type": "number", "description": "Target tab (from tabs_list). Operates on background tabs WITHOUT stealing focus or activating the window. Omit to use the first automation tab."}}

TOOLS = [
    {"name": "browser_status", "description": "Get real-time multi-backend status (Chrome, Obscura, Playwright) and selector cache metrics.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "browser_model", "description": "Extract structured zero-shot PageModel (interactive elements, forms, iframes, shadow roots, active dialogs) in compact markdown or JSON format.", "inputSchema": {"type": "object", "properties": {"format": {"type": "string", "enum": ["markdown", "json", "compact"]}, **TID}}},
    {"name": "browser_find", "description": "Find elements using Layer 0 Cache -> Layer 1 Deterministic -> Layer 2 Semantic -> Layer 3 Vision priority path.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "role": {"type": "string"}, "text": {"type": "string"}, "selector": {"type": "string"}, **TID}}},
    {"name": "browser_execute", "description": "Execute verified browser action (click, type, press, scroll, navigate) in <50ms with event-driven verification.", "inputSchema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["click", "type", "press", "navigate", "scroll"]}, "params": {"type": "object"}, "verify": {"type": "boolean"}, **TID}, "required": ["action"]}},
    {"name": "browser_detect_captcha", "description": "Check active tab for CAPTCHA barriers (Cloudflare Turnstile, reCAPTCHA, hCaptcha, Arkose).", "inputSchema": {"type": "object", "properties": {**TID}}},
    {"name": "tabs_list", "description": "List all open Chrome tabs (id, title, url).", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "tab_switch", "description": "Make a tab the active tab. Does NOT focus/raise the browser window unless focus:true is passed (pro tools never steal focus).", "inputSchema": {"type": "object", "properties": {"tabId": {"type": "number"}, "focus": {"type": "boolean"}}, "required": ["tabId"]}},
    {"name": "tab_create", "description": "Open a new tab (always in background, grouped under 'Muse automation').", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}}},
    {"name": "tab_close", "description": "Close a tab (default: active tab).", "inputSchema": {"type": "object", "properties": {"tabId": {"type": "number"}}}},
    {"name": "tab_group", "description": "Move tabs into a named tab group (creates 'Muse automation' group if needed).", "inputSchema": {"type": "object", "properties": {"tabIds": {"type": "array", "items": {"type": "number"}}, "title": {"type": "string"}}, "required": ["tabIds"]}},
    {"name": "bookmarks_tree", "description": "Read the FULL bookmark tree (titles + URLs) instantly via the bookmarks API. Zero UI, zero focus steal — the pro way; never automate chrome://bookmarks with mouse/keyboard.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "bookmarks_search", "description": "Search bookmarks by title/URL substring. Returns flat matches.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "snapshot", "description": "Snapshot interactive elements of a tab: refs with coords, role, name. Works on background tabs.", "inputSchema": {"type": "object", "properties": {**TID}}},
    {"name": "screenshot", "description": "Capture a PNG screenshot of a tab (works on background tabs, no activation needed).", "inputSchema": {"type": "object", "properties": {**TID}}},
    {"name": "som_mark", "description": "Draw numbered black labels over clickable elements; returns marks with coords. Use before pixel clicks.", "inputSchema": {"type": "object", "properties": {**TID}}},
    {"name": "som_clear", "description": "Remove numbered labels.", "inputSchema": {"type": "object", "properties": {**TID}}},
    {"name": "click", "description": "Trusted CDP click at x,y (or element ref from snapshot) on a background tab — no focus steal. Verifies the page changed afterwards.", "inputSchema": {"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "ref": {"type": "string"}, "verify": {"type": "boolean"}, **TID}}},
    {"name": "type", "description": "Type text into the focused element via CDP (works on background tabs).", "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}, **TID}, "required": ["text"]}},
    {"name": "press_key", "description": "Press a key: Enter, Tab, Escape, Backspace, Delete, Arrow keys, Home, End, PageUp, PageDown, or a single character.", "inputSchema": {"type": "object", "properties": {"key": {"type": "string"}, **TID}, "required": ["key"]}},
    {"name": "scroll", "description": "Scroll the page (deltaY>0 scrolls down).", "inputSchema": {"type": "object", "properties": {"deltaY": {"type": "number"}, "x": {"type": "number"}, "y": {"type": "number"}, **TID}}},
    {"name": "navigate", "description": "Navigate a tab to a URL (background-safe).", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, **TID}, "required": ["url"]}},
    {"name": "go_back", "description": "Browser back.", "inputSchema": {"type": "object", "properties": {**TID}}},
    {"name": "go_forward", "description": "Browser forward.", "inputSchema": {"type": "object", "properties": {**TID}}},
    {"name": "evaluate", "description": "Run JavaScript in the page (async fn body); returns the value. Background-safe.", "inputSchema": {"type": "object", "properties": {"js": {"type": "string"}, **TID}, "required": ["js"]}},
    {"name": "tab_adopt", "description": "Adopt an existing tab or current active tab into the 'Muse automation' tab group for automation.", "inputSchema": {"type": "object", "properties": {"tabId": {"type": "number"}}}},
    {"name": "cookies_export", "description": "Read all browser cookies via CDP Storage.getCookies through the debugger permission.", "inputSchema": {"type": "object", "properties": {**TID}}},
    {"name": "wait", "description": "Wait ms milliseconds.", "inputSchema": {"type": "object", "properties": {"ms": {"type": "number"}}}},
]


async def call_tool(name, args):
    args = args or {}
    if name == "browser_status":
        from core.cache import SelectorCache
        from core.router import BrowserRouter
        r = BrowserRouter()
        st = await r.health_check()
        c = SelectorCache()
        st["cache"] = c.stats()
        return st
    if name == "browser_model":
        from core.router import BrowserRouter
        from core.types import BrowserBackendType
        r = BrowserRouter()
        b = await r.resolve_backend(BrowserBackendType.AUTO)
        tabs = await b.list_tabs()
        tid = str(args.get("tabId") or (tabs[0]["tabId"] if tabs else ""))
        model = await b.build_page_model(tid)
        fmt = args.get("format", "markdown")
        if fmt == "json":
            return model.to_dict()
        elif fmt == "compact":
            return model.to_compact_dict()
        return {"markdown": model.to_markdown()}
    if name == "browser_find":
        from core.cache import SelectorCache
        from core.resolver import ElementResolver
        from core.router import BrowserRouter
        from core.types import BrowserBackendType, ElementQuery
        r = BrowserRouter()
        b = await r.resolve_backend(BrowserBackendType.AUTO)
        tabs = await b.list_tabs()
        tid = str(args.get("tabId") or (tabs[0]["tabId"] if tabs else ""))
        res = ElementResolver(cache=SelectorCache())
        q = ElementQuery(
            description=args.get("query"),
            name=args.get("query") or args.get("text"),
            role=args.get("role"),
            selector=args.get("selector"),
            text=args.get("text"),
        )
        el = await res.resolve(b, tid, q)
        if not el:
            return {"found": False}
        return {"found": True, "element": el.to_dict()}
    if name == "browser_execute":
        from core.router import BrowserRouter
        from core.types import BrowserBackendType
        r = BrowserRouter()
        b = await r.resolve_backend(BrowserBackendType.AUTO)
        tabs = await b.list_tabs()
        tid = str(args.get("tabId") or (tabs[0]["tabId"] if tabs else ""))
        act_res = await r.execute_action(
            tab_id=tid,
            action=args["action"],
            params=args.get("params"),
            verify=args.get("verify", True),
            backend=b,
        )
        return act_res.to_dict()
    if name == "browser_detect_captcha":
        from core.observability import CaptchaDetector
        from core.router import BrowserRouter
        from core.types import BrowserBackendType
        r = BrowserRouter()
        b = await r.resolve_backend(BrowserBackendType.AUTO)
        tabs = await b.list_tabs()
        tid = str(args.get("tabId") or (tabs[0]["tabId"] if tabs else ""))
        return await CaptchaDetector.detect(b, tid)
    if name == "tabs_list":
        return await call_ext("tabs.list")
    if name == "tab_switch":
        return await call_ext("tabs.switch", {"tabId": args["tabId"], **({"focus": True} if args.get("focus") else {})})
    if name == "tab_create":
        return await call_ext("tabs.create", {"url": args.get("url", "about:blank")})
    if name == "tab_close":
        return await call_ext("tabs.close", {"tabId": args.get("tabId")} if args.get("tabId") else {})
    if name == "tab_group":
        return await call_ext("tabs.group", {"tabIds": args["tabIds"], "title": args.get("title", "Muse automation")})
    if name == "bookmarks_tree":
        return await call_ext("bookmarks.tree")
    if name == "bookmarks_search":
        return await call_ext("bookmarks.search", {"query": args["query"]})
    tid = {"tabId": args["tabId"]} if args.get("tabId") else {}
    if name == "snapshot":
        return await do_snapshot(tid.get("tabId"))
    if name == "screenshot":
        res = await call_ext("page.screenshot", tid)
        # Save to file instead of returning huge base64 (bridge truncates at ~20k chars).
        # Copied from working tools: file-based screenshots for automation.
        if isinstance(res, dict) and res.get("dataUrl"):
            try:
                import base64, os, time
                b64 = res["dataUrl"].split(",", 1)[1]
                data = base64.b64decode(b64)
                shot_dir = os.path.join(os.path.expanduser("~"), "muse-browser-mcp", "shots")
                os.makedirs(shot_dir, exist_ok=True)
                path = os.path.join(shot_dir, f"shot_{int(time.time())}.png")
                with open(path, "wb") as f:
                    f.write(data)
                return {"path": path, "bytes": len(data)}
            except Exception as e:
                return {"error": f"save_failed: {e}"}
        return res
    if name == "som_mark":
        return await call_ext("page.som_mark", tid)
    if name == "som_clear":
        return await call_ext("page.som_clear", tid)
    if name == "click":
        return await tool_click({**args, **tid})
    if name == "type":
        return await call_ext("input.type", {"text": args["text"], **tid})
    if name == "press_key":
        return await call_ext("input.press_key", {"key": args["key"], **tid})
    if name == "scroll":
        d = {k: v for k, v in args.items() if v is not None and k != "tabId"}
        d.update(tid)
        return await call_ext("input.scroll", d)
    if name == "navigate":
        return await call_ext("page.navigate", {"url": args["url"], **tid})
    if name == "go_back":
        return await call_ext("page.back", tid)
    if name == "go_forward":
        return await call_ext("page.forward", tid)
    if name == "evaluate":
        return await call_ext("page.evaluate", {"js": args["js"], **tid})
    if name == "tab_adopt":
        return await call_ext("tabs.adopt", {"tabId": args.get("tabId")} if args.get("tabId") else {})
    if name == "cookies_export":
        return await call_ext("cookies.export_cdp", tid)
    if name == "wait":
        await asyncio.sleep((args.get("ms") or 500) / 1000.0)
        return {"waited_ms": args.get("ms") or 500}
    raise RuntimeError(f"unknown tool: {name}")


def mcp_text(payload):
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=1)[:20000]}]}


async def handle_mcp(req):
    method = req.get("method")
    rid = req.get("id")
    try:
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "muse-browser", "version": "1.0.0"}}}
        if method in ("notifications/initialized", "notifications/cancelled"):
            return None
        if method == "ping":
            return {"jsonrpc": "2.0", "id": rid, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
        if method == "tools/call":
            p = req.get("params", {})
            try:
                result = await call_tool(p.get("name"), p.get("arguments"))
                if p.get("name") == "screenshot" and isinstance(result, dict) and result.get("path"):
                    # Read the saved file and return as MCP image content
                    try:
                        import base64
                        with open(result["path"], "rb") as f:
                            b64 = base64.b64encode(f.read()).decode()
                        return {"jsonrpc": "2.0", "id": rid, "result": {
                            "content": [{"type": "image", "data": b64, "mimeType": "image/png"}]}}
                    except Exception:
                        pass  # fall through to text result with path
                return {"jsonrpc": "2.0", "id": rid, "result": mcp_text(result)}
            except Exception as e:
                return {"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text", "text": f"error: {e}"}], "isError": True}}
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"unknown method {method}"}}
    except Exception as e:
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32603, "message": str(e)}}


async def stdio_loop():
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        resp = await handle_mcp(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


async def main():
    global daemon_mode
    if is_daemon_running():
        daemon_mode = True
        print(f"[muse-browser] using running daemon at {DAEMON_HTTP_URL}", flush=True, file=sys.stderr)
        await stdio_loop()
    else:
        daemon_mode = False
        try:
            async with websockets.serve(ws_handler, WS_HOST, WS_PORT):
                print(f"[muse-browser] standalone ws on {WS_HOST}:{WS_PORT}", flush=True, file=sys.stderr)
                await stdio_loop()
        except OSError as e:
            if is_daemon_running():
                daemon_mode = True
                print(f"[muse-browser] ws port busy, connected via daemon {DAEMON_HTTP_URL}", flush=True, file=sys.stderr)
                await stdio_loop()
            else:
                raise RuntimeError(f"Could not bind ws://{WS_HOST}:{WS_PORT} and daemon is not running: {e}")


if __name__ == "__main__":
    asyncio.run(main())
