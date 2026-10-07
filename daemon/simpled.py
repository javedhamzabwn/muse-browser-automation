#!/usr/bin/env python3
"""daemon/simpled.py — Unified Single-Port Control Daemon for Muse 3.0.

EXPOSES EXACTLY ONE LOCAL PORT (127.0.0.1:18010) FOR ALL EXTERNAL & AGENT COMMUNICATION:
- /mcp: Model Context Protocol (MCP) HTTP/SSE JSON-RPC 2.0 endpoint
- /api/browser/...: Browser automation REST API (status, tabs, model, execute, find, screenshot)
- /ws: Multiplexed WebSocket on the SAME port (Chrome MV3 extension CDP & client streaming)
- /dashboard: Real-time Web Dashboard
- /health & /status: Unified multi-backend health checks
- /events: Server-Sent Events (SSE) action stream
- /tool: Backward-compatible legacy tool dispatcher
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import urllib.request
from typing import Any, Dict, List, Optional

import aiohttp
from aiohttp import web

# Add repo root to path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.cache import SelectorCache
from core.fetch.engine import UniversalFetchEngine
from core.observability import ActionTracer, CaptchaDetector
from core.page_model import PageModeler
from core.pool import BrowserPool
from core.resolver import ElementResolver
from core.risk_engine import RiskEngine
from core.router import BrowserRouter
from core.sessions.manager import ProfileManager
from core.task_engine import TaskEngine
from core.tools.health import SystemDoctor
from core.tools.registry import ToolRegistry
from core.types import ActionRiskLevel, BrowserBackendType, ElementQuery

logger = logging.getLogger("muse.daemon")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

HTTP_HOST = "127.0.0.1"
HTTP_PORT = int(os.environ.get("MUSE_PORT", 18010))
AUTH_TOKEN = os.environ.get("MUSE_AUTH_TOKEN", "").strip()

# Shared state
ext_ws: Optional[web.WebSocketResponse] = None
pending_cdp: Dict[int, asyncio.Future] = {}
cdp_seq = 0
tracer = ActionTracer(capacity=500)
cache = SelectorCache()
router = BrowserRouter()
pool = BrowserPool()
registry = ToolRegistry()
fetch_engine = UniversalFetchEngine(registry=registry)
task_engine = TaskEngine()
risk_engine = RiskEngine()
profile_mgr = ProfileManager()

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Muse Browser Automation 3.0 — Dashboard</title>
  <style>
    :root {
      --bg: #0f172a;
      --card: #1e293b;
      --card-hover: #24344d;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #38bdf8;
      --green: #22c55e;
      --red: #ef4444;
      --yellow: #f59e0b;
    }
    * { box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 24px; line-height: 1.5; }
    .header { display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 24px; flex-wrap: wrap; gap: 12px; }
    .title { font-size: 22px; font-weight: 700; display: flex; align-items: center; gap: 10px; }
    .badge { background: #064e3b; color: var(--green); padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; }
    .badge-port { background: #1e3a8a; color: var(--accent); padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
    .card-title { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; font-weight: 600; }
    .card-value { font-size: 20px; font-weight: 700; color: var(--text); }
    .card-sub { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
    .table-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-bottom: 24px; }
    table { width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }
    th { background: #0f172a; padding: 12px 16px; color: var(--text-muted); border-bottom: 1px solid var(--border); font-weight: 600; }
    td { padding: 12px 16px; border-bottom: 1px solid var(--border); }
    tr:last-child td { border-bottom: none; }
    .status-pill { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
    .status-ok { background: var(--green); box-shadow: 0 0 8px var(--green); }
    .status-off { background: var(--red); }
    .status-warn { background: var(--yellow); }
    code { background: #0f172a; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 12px; }
    .btn { background: #2563eb; color: #fff; border: none; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 600; transition: background 0.15s; }
    .btn:hover { background: #1d4ed8; }
    .btn-secondary { background: #334155; }
    .btn-secondary:hover { background: #475569; }
    .btn-danger { background: #dc2626; }
    .btn-danger:hover { background: #b91c1c; }
    .btn-group { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
  </style>
</head>
<body>
  <div class="header">
    <div class="title">
      <span class="status-pill status-ok"></span>
      Muse Browser Automation 4.0
      <span class="badge">Universal Fast Gateway</span>
      <span class="badge-port">Single Port :18010</span>
    </div>
    <div id="clock" style="color: var(--text-muted); font-size: 14px;"></div>
  </div>

  <div class="table-card" style="padding: 16px; margin-bottom: 24px;">
    <div style="font-weight: 700; font-size: 15px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
      <span>Exposure &amp; MCP Gateway Manager</span>
      <span id="exp-mode-badge" class="badge">LOCAL</span>
    </div>
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; font-size: 13px; margin-bottom: 16px;">
      <div><strong>Local Gateway:</strong> <code id="local-gw-url">http://127.0.0.1:18010</code></div>
      <div><strong>Local MCP:</strong> <code id="local-mcp-url">http://127.0.0.1:18010/mcp</code></div>
      <div><strong>Public URL:</strong> <code id="public-gw-url">Not exposed</code></div>
      <div><strong>Public MCP:</strong> <code id="public-mcp-url">Not exposed</code></div>
    </div>
    <div class="btn-group">
      <button class="btn btn-secondary" onclick="setMode('local')">Start Local</button>
      <button class="btn" onclick="setMode('ngrok')">Expose via ngrok</button>
      <button class="btn btn-danger" onclick="setMode('off')">Stop Public Exposure</button>
      <button class="btn btn-secondary" onclick="testMcp('local')">Test Local MCP</button>
      <button class="btn btn-secondary" onclick="testMcp('public')">Test Public MCP</button>
      <button class="btn btn-secondary" onclick="copyMcp('local')">Copy Local MCP</button>
      <button class="btn btn-secondary" onclick="copyMcp('public')">Copy Public MCP</button>
      <button class="btn btn-secondary" onclick="updateDashboard()">Refresh</button>
    </div>
    <div id="mcp-test-status" style="margin-top: 10px; font-size: 12px; color: var(--text-muted);"></div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="card-title">Remote Tunnel (ngrok)</div>
      <div class="card-value" id="ngrok-status">Checking...</div>
      <div class="card-sub" id="ngrok-url">Querying local agent</div>
    </div>
    <div class="card">
      <div class="card-title">Chrome Extension Bridge</div>
      <div class="card-value" id="ext-status">Checking...</div>
      <div class="card-sub">ws://127.0.0.1:18010/ws</div>
    </div>
    <div class="card">
      <div class="card-title">Playwright Chromium</div>
      <div class="card-value" id="pw-status">Checking...</div>
      <div class="card-sub">Fast Path (&lt;20ms)</div>
    </div>
    <div class="card">
      <div class="card-title">Learned Selector Cache</div>
      <div class="card-value" id="cache-entries">0 entries</div>
      <div class="card-sub" id="cache-stats">0 hits / 0 fails</div>
    </div>
  </div>

  <div class="table-card">
    <div style="padding: 16px; font-weight: 600; border-bottom: 1px solid var(--border);">Active Endpoints (Multiplexed on 18010)</div>
    <table>
      <thead>
        <tr>
          <th>Endpoint</th>
          <th>Protocol</th>
          <th>Description</th>
        </tr>
      </thead>
      <tbody>
        <tr><td><code>/mcp</code></td><td>HTTP POST / SSE</td><td>Model Context Protocol (JSON-RPC 2.0)</td></tr>
        <tr><td><code>/api/browser/...</code></td><td>REST HTTP</td><td>Zero-shot PageModel, verified click, find, tabs</td></tr>
        <tr><td><code>/ws</code></td><td>WebSocket</td><td>Extension CDP bridge &amp; telemetry streaming</td></tr>
        <tr><td><code>/dashboard</code></td><td>HTTP GET</td><td>This interactive monitoring dashboard</td></tr>
        <tr><td><code>/health &amp; /status</code></td><td>HTTP GET</td><td>Single-point health check across all backends</td></tr>
      </tbody>
    </table>
  </div>

  <div class="table-card">
    <div style="padding: 16px; font-weight: 600; border-bottom: 1px solid var(--border);">Recent Automation Traces</div>
    <table>
      <thead>
        <tr>
          <th>Time</th>
          <th>Action</th>
          <th>Duration</th>
          <th>Verified</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody id="trace-rows">
        <tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 24px;">No recent actions recorded</td></tr>
      </tbody>
    </table>
  </div>

  <script>
    async function updateDashboard() {
      document.getElementById('clock').textContent = new Date().toLocaleTimeString();
      try {
        const res = await fetch('/status');
        const data = await res.json();

        // ngrok
        const ng = data.ngrok || {};
        if (ng.connected) {
          document.getElementById('ngrok-status').textContent = 'Connected';
          document.getElementById('ngrok-status').style.color = 'var(--green)';
          document.getElementById('ngrok-url').textContent = ng.public_url;
        } else {
          document.getElementById('ngrok-status').textContent = 'Not Connected';
          document.getElementById('ngrok-status').style.color = 'var(--text-muted)';
          document.getElementById('ngrok-url').textContent = 'run: ngrok http 18010';
        }

        // Chrome extension
        const ch = data.components?.chrome || {};
        document.getElementById('ext-status').textContent = ch.connected ? 'Connected' : 'Offline';
        document.getElementById('ext-status').style.color = ch.connected ? 'var(--green)' : 'var(--text-muted)';

        // Playwright
        const pw = data.components?.playwright || {};
        document.getElementById('pw-status').textContent = pw.available ? 'Ready' : 'Not Installed';
        document.getElementById('pw-status').style.color = pw.available ? 'var(--green)' : 'var(--text-muted)';

        // Cache
        const c = data.components?.cache || {};
        document.getElementById('cache-entries').textContent = (c.total_entries || 0) + ' entries';
        document.getElementById('cache-stats').textContent = (c.total_successes || 0) + ' hits / ' + (c.total_failures || 0) + ' fails';
      } catch (e) {}

      try {
        const expRes = await fetch('/api/exposure/status');
        const expData = await expRes.json();
        const exp = expData.result || {};
        const mode = exp.exposure?.mode || 'local';
        document.getElementById('exp-mode-badge').textContent = mode.toUpperCase();

        let pUrl = exp.exposure?.public_url;
        let pMcp = exp.exposure?.public_mcp;
        if (!pUrl && data.ngrok && data.ngrok.connected && mode !== 'off') {
          pUrl = data.ngrok.public_url;
          pMcp = data.ngrok.remote_mcp_url || (pUrl + '/mcp');
        }

        if (pUrl) {
          document.getElementById('public-gw-url').innerHTML = `<a href="${pUrl}" target="_blank" style="color:#60a5fa; text-decoration:none;">${pUrl}</a>`;
          document.getElementById('public-mcp-url').innerHTML = `<a href="${pMcp}" target="_blank" style="color:#60a5fa; text-decoration:none;">${pMcp}</a>`;
        } else {
          document.getElementById('public-gw-url').textContent = 'Not exposed';
          document.getElementById('public-mcp-url').textContent = 'Not exposed';
        }
      } catch (e) {}

      try {
        const trRes = await fetch('/api/browser/traces');
        const traces = await trRes.json();
        if (traces && traces.length > 0) {
          const tbody = document.getElementById('trace-rows');
          tbody.innerHTML = traces.slice().reverse().slice(0, 15).map(t => `
            <tr>
              <td>${new Date(t.timestamp * 1000).toLocaleTimeString()}</td>
              <td><code>${t.action}</code></td>
              <td>${t.duration_ms}ms</td>
              <td>${t.details && t.details.verified ? '✅ Yes' : '—'}</td>
              <td><span style="color: ${t.ok ? 'var(--green)' : 'var(--red)'}">${t.ok ? 'OK' : (t.error || 'Failed')}</span></td>
            </tr>
          `).join('');
        }
      } catch (e) {}
    }

    async function setMode(targetMode) {
      document.getElementById('mcp-test-status').textContent = 'Switching mode to ' + targetMode + '...';
      try {
        const r = await fetch('/api/exposure/mode', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({mode: targetMode})
        });
        const res = await r.json();
        if (res.ok && res.result) {
          const exp = res.result;
          document.getElementById('mcp-test-status').textContent = 'Mode switched to ' + targetMode;
          document.getElementById('exp-mode-badge').textContent = (exp.mode || targetMode).toUpperCase();
          if (exp.public_url) {
            document.getElementById('public-gw-url').innerHTML = `<a href="${exp.public_url}" target="_blank" style="color:#60a5fa; text-decoration:none;">${exp.public_url}</a>`;
            const pmcp = exp.public_mcp || (exp.public_url + '/mcp');
            document.getElementById('public-mcp-url').innerHTML = `<a href="${pmcp}" target="_blank" style="color:#60a5fa; text-decoration:none;">${pmcp}</a>`;
          } else {
            document.getElementById('public-gw-url').textContent = 'Not exposed';
            document.getElementById('public-mcp-url').textContent = 'Not exposed';
          }
        } else {
          document.getElementById('mcp-test-status').textContent = 'Error: ' + (res.error || 'Failed to switch mode');
        }
        await updateDashboard();
      } catch (e) {
        document.getElementById('mcp-test-status').textContent = 'Request failed: ' + e;
      }
    }

    async function testMcp(scope) {
      document.getElementById('mcp-test-status').textContent = 'Testing ' + scope + ' MCP endpoint...';
      try {
        const targetUrl = (scope === 'public' ? document.getElementById('public-mcp-url').textContent : '/mcp').trim();
        if (!targetUrl || targetUrl.includes('Not exposed')) {
          document.getElementById('mcp-test-status').textContent = 'Public MCP is not exposed. Enable ngrok first.';
          return;
        }
        const t0 = performance.now();
        const r = await fetch(targetUrl, {
          method: 'POST',
          headers: {'Content-Type': 'application/json', 'ngrok-skip-browser-warning': '1'},
          body: JSON.stringify({jsonrpc: '2.0', id: 1, method: 'tools/list', params: {}})
        });
        const dt = Math.round(performance.now() - t0);
        const data = await r.json();
        const count = data.result?.tools?.length || 0;
        document.getElementById('mcp-test-status').textContent = `[PASS] ${scope.toUpperCase()} MCP OK (${count} tools, ${dt}ms)`;
      } catch (e) {
        document.getElementById('mcp-test-status').textContent = `[FAIL] ${scope.toUpperCase()} MCP test failed: ` + e;
      }
    }

    function copyMcp(scope) {
      const url = (scope === 'public' ? document.getElementById('public-mcp-url').textContent : document.getElementById('local-mcp-url').textContent).trim();
      if (!url || url.includes('Not exposed')) {
        alert('Public MCP is not exposed');
        return;
      }
      navigator.clipboard.writeText(url).then(() => {
        document.getElementById('mcp-test-status').textContent = 'Copied ' + url + ' to clipboard!';
      }).catch(() => {
        document.getElementById('mcp-test-status').textContent = 'URL: ' + url;
      });
    }

    updateDashboard();
    setInterval(updateDashboard, 2500);
  </script>
</body>
</html>
"""


def detect_ngrok_status() -> Dict[str, Any]:
    """Detect if local ngrok client is running on standard port 4040."""
    try:
        req = urllib.request.Request("http://127.0.0.1:4040/api/tunnels")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            tunnels = data.get("tunnels", [])
            for t in tunnels:
                proto = t.get("proto")
                purl = t.get("public_url", "")
                addr = str(t.get("config", {}).get("addr", ""))
                if purl and (proto == "https" or purl.startswith("https://")) and str(HTTP_PORT) in addr:
                    return {
                        "connected": True,
                        "public_url": purl,
                        "remote_mcp_url": f"{purl}/mcp",
                        "local_addr": addr,
                    }
    except Exception:
        pass
        return {"connected": False, "public_url": None, "remote_mcp_url": None}


async def call_extension(method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Dict[str, Any]:
    """Send CDP command to Chrome MV3 extension over WebSocket."""
    global ext_ws, cdp_seq
    if ext_ws is None or ext_ws.closed:
        return {"ok": False, "error": "Chrome extension not connected to daemon"}

    cdp_seq += 1
    mid = cdp_seq
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    pending_cdp[mid] = fut

    msg = json.dumps({"id": mid, "method": method, "params": params or {}})
    t0 = time.perf_counter()
    try:
        await ext_ws.send_str(msg)
        res = await asyncio.wait_for(fut, timeout=timeout)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        ok = bool(res.get("ok"))
        tracer.record(action=method, duration_ms=dt_ms, ok=ok, tab_id="chrome_ext", error=res.get("error"))
        return res
    except Exception as exc:
        dt_ms = (time.perf_counter() - t0) * 1000.0
        tracer.record(action=method, duration_ms=dt_ms, ok=False, tab_id="chrome_ext", error=str(exc))
        return {"ok": False, "error": str(exc)}
    finally:
        pending_cdp.pop(mid, None)


# ---------------- HTTP Request Handlers ----------------

def verify_auth(request: web.Request) -> bool:
    if not AUTH_TOKEN:
        return True
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip() if auth.startswith("Bearer ") else ""
    if not token:
        token = request.headers.get("X-Muse-Token", "").strip()
    return token == AUTH_TOKEN


_last_health_status: Optional[Dict[str, Any]] = None
_last_health_time: float = 0.0


async def get_cached_backend_health() -> Dict[str, Any]:
    global _last_health_status, _last_health_time
    now = time.time()
    if _last_health_status is None or (now - _last_health_time) > 10.0:
        _last_health_status = await router.health_check()
        _last_health_time = now
    return _last_health_status


async def handle_health(request: web.Request) -> web.Response:
    if not verify_auth(request):
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)

    r_status = await get_cached_backend_health()
    ngrok = detect_ngrok_status()

    payload = {
        "ok": True,
        "status": "healthy",
        "version": "3.0.0",
        "single_port": HTTP_PORT,
        "mcp_url": f"http://{HTTP_HOST}:{HTTP_PORT}/mcp",
        "ngrok": ngrok,
        "ext": ext_ws is not None and not ext_ws.closed,
        "components": {
            "mcp": True,
            "daemon": True,
            "chrome": {
                "available": r_status.get("chrome", {}).get("available", False),
                "connected": ext_ws is not None and not ext_ws.closed,
            },
            "obscura": r_status.get("obscura", {}),
            "playwright": r_status.get("playwright", {}),
            "cache": cache.stats(),
            "workspaces": len(pool.list_workspaces()),
        },
    }
    return web.json_response(payload)


async def handle_dashboard(request: web.Request) -> web.Response:
    return web.Response(text=DASHBOARD_HTML, content_type="text/html")


async def handle_events_sse(request: web.Request) -> web.StreamResponse:
    """Stream real-time action events using Server-Sent Events (SSE)."""
    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )
    await response.prepare(request)
    await response.write(b": keep-alive\n\n")

    try:
        last_seen = 0.0
        while True:
            recent = tracer.get_recent(10)
            for t in recent:
                if t["timestamp"] > last_seen:
                    data = json.dumps(t)
                    await response.write(f"data: {data}\n\n".encode("utf-8"))
                    last_seen = t["timestamp"]
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        pass
    return response


async def handle_ws(request: web.Request) -> web.WebSocketResponse:
    """Multiplexed WebSocket handler on port 18010."""
    global ext_ws
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    logger.info("WebSocket connected on unified port %d", HTTP_PORT)
    ext_ws = ws

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except Exception:
                    continue
                if data.get("type") == "ping":
                    await ws.send_json({"type": "pong", "data": data.get("data")})
                    continue
                mid = data.get("id")
                if mid is not None and mid in pending_cdp:
                    fut = pending_cdp.pop(mid)
                    if not fut.done():
                        fut.set_result(data)
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break
    finally:
        if ext_ws is ws:
            ext_ws = None
        logger.info("WebSocket disconnected from unified port %d", HTTP_PORT)
    return ws


# ---------------- MCP Implementation on /mcp ----------------

MCP_TOOLS = [
    {
        "name": "browser_task",
        "description": "Execute multi-step autonomous browser workflow with state checkpoints, loop governor, and failure recovery.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string"
                },
                "actions": {
                    "type": "array",
                    "items": {
                        "type": "object"
                    }
                },
                "taskId": {
                    "type": "string"
                },
                "profile": {
                    "type": "string"
                },
                "approved": {
                    "type": "boolean"
                }
            }
        }
    },
    {
        "name": "browser_open",
        "description": "Open or navigate browser tab to URL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string"
                },
                "tabId": {
                    "type": "string"
                },
                  "backend": {"type": "string", "description": "Optional browser backend override (e.g. \'csi\', \'chrome\')" },
                "backend": {
                    "type": "string"
                },
                "backend": {
                    "type": "string",
                    "description": "Optional browser backend override (e.g. 'playwright', 'camoufox', 'csi'). Uses automatic routing if omitted."
                }
            },
            "required": [
                "url"
            ]
        }
    },
    {
        "name": "browser_extract",
        "description": "Extract structured content, markdown, interactive elements, or text from active or specified URL/tab.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string"
                },
                "tabId": {
                    "type": "string"
                },
                  "backend": {"type": "string", "description": "Optional browser backend override (e.g. \'csi\', \'chrome\')" },
                "backend": {
                    "type": "string"
                },
                "format": {
                    "type": "string",
                    "enum": [
                        "markdown",
                        "json",
                        "compact"
                    ]
                },
                "backend": {
                    "type": "string",
                    "description": "Optional browser backend override (e.g. 'playwright', 'camoufox', 'csi'). Uses automatic routing if omitted."
                }
            }
        }
    },
    {
        "name": "browser_find",
        "description": "Find elements using Layer 0 Cache -> Layer 1 Deterministic -> Layer 2 Semantic -> Layer 3 Vision priority path.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string"
                },
                "role": {
                    "type": "string"
                },
                "text": {
                    "type": "string"
                },
                "selector": {
                    "type": "string"
                },
                "tabId": {
                    "type": "string"
                },
                  "backend": {"type": "string", "description": "Optional browser backend override (e.g. \'csi\', \'chrome\')" },
                "backend": {
                    "type": "string"
                },
                "backend": {
                    "type": "string",
                    "description": "Optional browser backend override (e.g. 'playwright', 'camoufox', 'csi'). Uses automatic routing if omitted."
                }
            }
        }
    },
    {
        "name": "browser_fill",
        "description": "Focus an input, clear its current value, and type the new text. Best for form filling.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "text": {"type": "string", "description": "The text to type"},
                "x": {"type": "number"},
                "y": {"type": "number"},
                "tabId": {"type": "string"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "browser_submit",
        "description": "Trigger a form submission by finding the nearest form to the element and calling .submit().",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "x": {"type": "number"},
                "y": {"type": "number"},
                "tabId": {"type": "string"}
            }
        }
    },
    {
        "name": "browser_wait",
        "description": "Wait for an element (by selector or text) to appear on the page.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "text": {"type": "string"},
                "timeout": {"type": "number", "description": "Timeout in milliseconds. Default 5000."}
            }
        }
    },
    {
        "name": "browser_select",
        "description": "Select an option in a native <select> dropdown.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "text": {"type": "string"},
                "value": {"type": "string", "description": "The value to select"},
                "tabId": {"type": "string"},
                "backend": {"type": "string"}
            },
            "required": ["value"]
        }
    },
    {
        "name": "browser_evaluate",
        "description": "Evaluate raw Javascript in the active page context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "js": {"type": "string", "description": "Javascript string to evaluate"},
                "tabId": {"type": "string"},
                "backend": {"type": "string"}
            },
            "required": ["js"]
        }
    },
    {
        "name": "browser_click",
        "description": "Click element via coordinates or selector with event-driven DOM verification (<50ms).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "x": {
                    "type": "number"
                },
                "y": {
                    "type": "number"
                },
                "selector": {
                    "type": "string"
                },
                "text": {
                    "type": "string"
                },
                "tabId": {
                    "type": "string"
                },
                  "backend": {"type": "string", "description": "Optional browser backend override (e.g. \'csi\', \'chrome\')" },
                "backend": {
                    "type": "string"
                }
            }
        }
    },
    {
        "name": "browser_type",
        "description": "Type text into focused element.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string"
                },
                "tabId": {
                    "type": "string"
                },
                  "backend": {"type": "string", "description": "Optional browser backend override (e.g. \'csi\', \'chrome\')" },
                "backend": {
                    "type": "string"
                }
            },
            "required": [
                "text"
            ]
        }
    },
    {
        "name": "browser_scroll",
        "description": "Scroll active tab vertically or horizontally.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": [
                        "up",
                        "down"
                    ]
                },
                "amount": {
                    "type": "number"
                },
                "tabId": {
                    "type": "string"
                },
                  "backend": {"type": "string", "description": "Optional browser backend override (e.g. \'csi\', \'chrome\')" },
                "backend": {
                    "type": "string"
                }
            }
        }
    },
    {
        "name": "browser_screenshot",
        "description": "Capture PNG screenshot of tab.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tabId": {
                    "type": "string"
                },
                  "backend": {"type": "string", "description": "Optional browser backend override (e.g. \'csi\', \'chrome\')" },
                "backend": {
                    "type": "string"
                }
            }
        }
    },
    {
        "name": "browser_tabs",
        "description": "List, switch, create, or close browser tabs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "list",
                        "switch",
                        "create",
                        "close"
                    ]
                },
                "tabId": {
                    "type": "string"
                },
                  "backend": {"type": "string", "description": "Optional browser backend override (e.g. \'csi\', \'chrome\')" },
                "backend": {
                    "type": "string"
                },
                "url": {
                    "type": "string"
                }
            }
        }
    },
    {
        "name": "browser_status",
        "description": "Get real-time multi-backend status (Chrome, Obscura, Playwright) and selector cache metrics.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "browser_health",
        "description": "Run multi-backend health checks across browsers.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "browser_task_status",
        "description": "Inspect status of an asynchronous managed task (running, waiting_approval, waiting_human, completed, failed).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "taskId": {
                    "type": "string"
                }
            },
            "required": [
                "taskId"
            ]
        }
    },
    {
        "name": "browser_task_cancel",
        "description": "Cancel an active or queued browser task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "taskId": {
                    "type": "string"
                }
            },
            "required": [
                "taskId"
            ]
        }
    },
    {
        "name": "fetch_url",
        "description": "Universal multi-tier fetcher with automatic fallback (HTTP -> Lightweight -> JS -> Real Browser -> Redlib).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string"
                },
                "requirements": {
                    "type": "object",
                    "description": "Optional requirements e.g., {'javascript': True} or {'backend': 'redlib'} to force a specific tool."
                },
                "options": {
                    "type": "object"
                }
            },
            "required": [
                "url"
            ]
        }
    },
    {
        "name": "fetch_extract",
        "description": "Fetch web page and extract clean structured text and links without DOM bloat.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string"
                },
                "requirements": {
                    "type": "object",
                    "description": "Optional requirements e.g., {'javascript': True} or {'backend': 'redlib'} to force a specific tool."
                }
            },
            "required": [
                "url"
            ]
        }
    },
    {
        "name": "tool_status",
        "description": "List all registered browsers, fetchers, computer tools, and utilities with their capability and health states.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "tool_health",
        "description": "Run live diagnostic health checks across all registered platform tools.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "computer_click",
        "description": "Move cursor and click at desktop coordinates (x, y) using native Windows automation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "x": {
                    "type": "number"
                },
                "y": {
                    "type": "number"
                },
                "button": {
                    "type": "string",
                    "enum": [
                        "left",
                        "right",
                        "middle"
                    ]
                },
                "clicks": {
                    "type": "integer"
                }
            },
            "required": [
                "x",
                "y"
            ]
        }
    },
    {
        "name": "computer_type",
        "description": "Type text string into active desktop window.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string"
                }
            },
            "required": [
                "text"
            ]
        }
    },
    {
        "name": "computer_screenshot",
        "description": "Capture full desktop screenshot as base64 PNG.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "computer_windows",
        "description": "List all open desktop application windows with handles and bounds.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "tools_install",
        "description": "Install one or all external tools idempotently into the controlled workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string"
                }
            },
            "required": [
                "tool_name"
            ]
        }
    },
    {
        "name": "tools_test",
        "description": "Run standard functional test contract on an installed tool.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string"
                }
            },
            "required": [
                "tool_name"
            ]
        }
    },
    {
        "name": "tools_benchmark",
        "description": "Run latency and performance benchmark across tools.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string"
                },
                "category": {
                    "type": "string",
                    "enum": [
                        "browser",
                        "computer",
                        "media",
                        "all"
                    ]
                }
            }
        }
    },
    {
        "name": "tools_audit",
        "description": "Perform deep technical audit and code inspection of tool repository.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string"
                }
            }
        }
    },
    {
        "name": "tools_configure",
        "description": "Configure preferred backend or override for tool categories.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string"
                },
                "backend": {
                    "type": "string"
                },
                "preference": {
                    "type": "string",
                    "enum": [
                        "preferred",
                        "fallback",
                        "disabled"
                    ]
                }
            }
        }
    },
    {
        "name": "browser_model",
        "description": "Extract structured zero-shot PageModel in compact markdown or JSON format.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": [
                        "markdown",
                        "json",
                        "compact"
                    ]
                },
                "tabId": {
                    "type": "string"
                },
                  "backend": {"type": "string", "description": "Optional browser backend override (e.g. \'csi\', \'chrome\')" },
                "backend": {
                    "type": "string"
                },
                "backend": {
                    "type": "string",
                    "description": "Optional browser backend override (e.g. 'playwright', 'camoufox', 'csi'). Uses automatic routing if omitted."
                }
            }
        }
    },
    {
        "name": "browser_execute",
        "description": "Execute verified browser action (click, type, press, scroll, navigate) in <50ms with event-driven verification.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "click",
                        "type",
                        "press",
                        "navigate",
                        "scroll"
                    ]
                },
                "params": {
                    "type": "object"
                },
                "verify": {
                    "type": "boolean"
                },
                "tabId": {
                    "type": "string"
                },
                  "backend": {"type": "string", "description": "Optional browser backend override (e.g. \'csi\', \'chrome\')" },
                "backend": {
                    "type": "string"
                },
                "backend": {
                    "type": "string",
                    "description": "Optional browser backend override (e.g. 'playwright', 'camoufox', 'csi'). Uses automatic routing if omitted."
                }
            },
            "required": [
                "action"
            ]
        }
    },
    {
        "name": "browser_detect_captcha",
        "description": "Check active tab for CAPTCHA barriers (Cloudflare Turnstile, reCAPTCHA, hCaptcha, Arkose).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tabId": {
                    "type": "string"
                },
                  "backend": {"type": "string", "description": "Optional browser backend override (e.g. \'csi\', \'chrome\')" },
                "backend": {
                    "type": "string"
                },
                "backend": {
                    "type": "string",
                    "description": "Optional browser backend override (e.g. 'playwright', 'camoufox', 'csi'). Uses automatic routing if omitted."
                }
            }
        }
    },
    {
        "name": "tabs_list",
        "description": "List all active tabs across automation browsers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "backend": {
                    "type": "string",
                    "description": "Optional browser backend override (e.g. 'playwright', 'camoufox', 'csi'). Uses automatic routing if omitted."
                }
            }
        }
    },
    {
        "name": "tab_switch",
        "description": "Switch active tab without stealing window focus.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tabId": {
                    "type": "string"
                },
                  "backend": {"type": "string", "description": "Optional browser backend override (e.g. \'csi\', \'chrome\')" },
                "backend": {
                    "type": "string"
                },
                "focus": {
                    "type": "boolean"
                },
                "backend": {
                    "type": "string",
                    "description": "Optional browser backend override (e.g. 'playwright', 'camoufox', 'csi'). Uses automatic routing if omitted."
                }
            },
            "required": [
                "tabId"
            ]
        }
    },
    {
        "name": "tab_create",
        "description": "Create new browser tab.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string"
                },
                "backend": {
                    "type": "string",
                    "description": "Optional browser backend override (e.g. 'playwright', 'camoufox', 'csi'). Uses automatic routing if omitted."
                }
            }
        }
    },
    {
        "name": "tab_close",
        "description": "Close browser tab.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tabId": {
                    "type": "string"
                },
                  "backend": {"type": "string", "description": "Optional browser backend override (e.g. \'csi\', \'chrome\')" },
                "backend": {
                    "type": "string"
                },
                "backend": {
                    "type": "string",
                    "description": "Optional browser backend override (e.g. 'playwright', 'camoufox', 'csi'). Uses automatic routing if omitted."
                }
            }
        }
    },
    {
        "name": "navigate",
        "description": "Navigate active or specified tab to URL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string"
                },
                "tabId": {
                    "type": "string"
                },
                  "backend": {"type": "string", "description": "Optional browser backend override (e.g. \'csi\', \'chrome\')" },
                "backend": {
                    "type": "string"
                },
                "backend": {
                    "type": "string",
                    "description": "Optional browser backend override (e.g. 'playwright', 'camoufox', 'csi'). Uses automatic routing if omitted."
                }
            },
            "required": [
                "url"
            ]
        }
    },
    {
        "name": "click",
        "description": "Click element via coordinates or selector with verified UI transition.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "x": {
                    "type": "number"
                },
                "y": {
                    "type": "number"
                },
                "selector": {
                    "type": "string"
                },
                "text": {
                    "type": "string"
                },
                "tabId": {
                    "type": "string"
                },
                  "backend": {"type": "string", "description": "Optional browser backend override (e.g. \'csi\', \'chrome\')" },
                "backend": {
                    "type": "string"
                },
                "backend": {
                    "type": "string",
                    "description": "Optional browser backend override (e.g. 'playwright', 'camoufox', 'csi'). Uses automatic routing if omitted."
                }
            }
        }
    },
    {
        "name": "type",
        "description": "Type text into focused element.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string"
                },
                "tabId": {
                    "type": "string"
                },
                  "backend": {"type": "string", "description": "Optional browser backend override (e.g. \'csi\', \'chrome\')" },
                "backend": {
                    "type": "string"
                },
                "backend": {
                    "type": "string",
                    "description": "Optional browser backend override (e.g. 'playwright', 'camoufox', 'csi'). Uses automatic routing if omitted."
                }
            },
            "required": [
                "text"
            ]
        }
    },
    {
        "name": "screenshot",
        "description": "Capture PNG screenshot of tab.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tabId": {
                    "type": "string"
                },
                  "backend": {"type": "string", "description": "Optional browser backend override (e.g. \'csi\', \'chrome\')" },
                "backend": {
                    "type": "string"
                },
                "backend": {
                    "type": "string",
                    "description": "Optional browser backend override (e.g. 'playwright', 'camoufox', 'csi'). Uses automatic routing if omitted."
                }
            }
        }
    },
    {
        "name": "session_list",
        "description": "List stored browser sessions metadata (domains, allowed tools, status) without revealing tokens.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string"
                }
            }
        }
    },
    {
        "name": "session_import",
        "description": "Import domain-scoped browser cookies into AES-GCM-256 encrypted session vault.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "browser": {
                    "type": "string"
                },
                "profile": {
                    "type": "string"
                },
                "domains": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    }
                },
                "allowed_tools": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    }
                },
                "name": {
                    "type": "string"
                }
            },
            "required": [
                "domains"
            ]
        }
    },
    {
        "name": "session_validate",
        "description": "Test stored session online validity without leaking credentials and update status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string"
                },
                "domain": {
                    "type": "string"
                }
            },
            "required": [
                "session_id"
            ]
        }
    },
    {
        "name": "session_revoke",
        "description": "Revoke session and permanently erase encrypted key and payload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string"
                }
            },
            "required": [
                "session_id"
            ]
        }
    },
    {
        "name": "tools_validate",
        "description": "Execute comprehensive 6-category real-world validation matrix and generate reports.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]



async def call_csi(action: str, args: dict) -> dict:
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("http://127.0.0.1:10088/command", json={"action": action, "args": args}, timeout=15) as resp:
                data = await resp.json()
                if not data.get("success"):
                    err = data.get("error", "Unknown CSI error")
                    if "extension not connected" in str(err).lower():
                        raise Exception("WATCHDOG ALERT: The CSI bridge (port 10088) is running, but its Chrome extension disconnected. You must refresh/re-open the CSI Chrome profile to restore this backend.")
                    raise Exception(err)
                return data.get("data")
    except Exception as e:
        raise Exception(f"CSI backend error: {e}")

async def dispatch_tool_call(name: str, args: Dict[str, Any]) -> Any:
    args = args or {}
    pref = args.get('backend', 'auto')
    
    # Force chrome backend for native evaluation tools only if backend not explicitly provided
    if "backend" not in args and name in ("select", "browser_select", "evaluate", "browser_evaluate", "browser_find", "browser_extract", "browser_fill", "browser_submit", "browser_wait", "browser_screenshot"):
        pref = "chrome"
    
    # If explicitly targeting CSI from within the daemon, bypass the HTTP proxy
    if pref.lower() == "chrome":
        # Muse Native Extension (ext_ws)
        
        # Bug Fix 3: Ensure tabId is an integer to prevent Chrome API crashes
        if "tabId" in args and isinstance(args["tabId"], str) and args["tabId"].isdigit():
            args["tabId"] = int(args["tabId"])

        if name in ("browser_tabs", "tabs_list"):
            return await call_extension("tabs.list", args)
        elif name == "browser_open":
            # Bug Fix 1: Ensure URL is passed correctly and tab becomes active
            url = args.get("url", "about:blank")
            if "url" not in args and "params" in args:
                url = args["params"].get("url", url)
            return await call_extension("tabs.create", {"url": url, "active": False}) 
        elif name == "navigate":
            return await call_extension("page.navigate", args)
        elif name == "tab_switch": return await call_extension("tabs.switch", args)
        elif name == "tab_create": return await call_extension("tabs.create", {"url": args.get("url", "about:blank"), "active": False})
        elif name == "tab_close": return await call_extension("tabs.close", args)
        elif name in ("scroll", "browser_scroll"): return await call_extension("input.scroll", args)
        elif name in ("screenshot", "browser_screenshot"): return await call_extension("page.screenshot", args)
        elif name in ("browser_evaluate", "evaluate"):
            return await call_extension("page.evaluate", args)
        elif name in ("browser_model", "browser_find", "browser_extract", "click", "browser_click", "type", "browser_type", "select", "browser_select", "browser_fill", "browser_submit", "browser_wait"):
            
            needs_snap = name in ("browser_model", "browser_find", "browser_extract", "click", "browser_click", "select", "browser_select", "browser_fill", "browser_submit") and ("x" not in args and "y" not in args)
            snap = await call_extension("page.snapshot", args) if needs_snap else {}
            res = snap.get("result", snap) if snap else {}
            elements = res.get("elements", [])
            
            if name == "browser_model":
                lines = [f"# {res.get('title', '')}", f"URL: {res.get('url', '')}", ""]
                for el in elements:
                    lines.append(f"- [{el.get('ref', '')}] {el.get('role', '')} '{el.get('name', '')}'")
                return {"markdown": chr(10).join(lines)}
                
            elif name in ("browser_find", "browser_extract"):
                sel = args.get("selector", "")
                txt = args.get("query", args.get("text", ""))
                found = []
                for el in elements:
                    if sel and (el.get("ref") == sel or el.get("tag") == sel): found.append(el)
                    elif txt and txt.lower() in el.get("name", "").lower(): found.append(el)
                return {"found": bool(found), "elements": found}
                
            elif name in ("click", "browser_click", "select", "browser_select", "browser_fill", "browser_submit"):
                if "x" not in args and "y" not in args:
                    sel = args.get("selector", "")
                    txt = args.get("text", args.get("query", ""))
                    target = None
                    for el in elements:
                        if sel and (el.get("ref") == sel or el.get("tag") == sel):
                            target = el
                            break
                        if txt and txt.lower() in el.get("name", "").lower():
                            target = el
                            break
                    if not target:
                        return {"ok": False, "error": f"Could not find element matching selector='{sel}' or text='{txt}'"}
                    args["x"] = target["x"]
                    args["y"] = target["y"]
                    args["_is_css"] = True
                
                if name in ("click", "browser_click"):
                    return await call_extension("input.click", args)
                elif name in ("select", "browser_select"):
                    val = args.get("value", "").replace("'", "\'")
                    is_css = args.get("_is_css", False)
                    # If x,y were populated from the selector, they are already CSS pixels. 
                    # If provided by the AI, they are in the 1000-based normalized space.
                    sx = args['x'] if is_css else f"({args['x']} / 1000) * window.innerWidth"
                    sy = args['y'] if is_css else f"({args['y']} / 1000) * window.innerHeight"
                    js = f"(() => {{ let el = document.elementFromPoint({sx}, {sy}); if(el){{ el.value = '{val}'; el.dispatchEvent(new Event('change', {{bubbles: true}})); return el.value; }} return null; }})()"
                    args["js"] = js
                    return await call_extension("page.evaluate", args)
                elif name == "browser_fill":
                    is_css = args.get("_is_css", False)
                    sx = args['x'] if is_css else f"({args['x']} / 1000) * window.innerWidth"
                    sy = args['y'] if is_css else f"({args['y']} / 1000) * window.innerHeight"
                    js = f"let el = document.elementFromPoint({sx}, {sy}); if(el) {{ el.focus(); el.value = ''; el.dispatchEvent(new Event('input', {{bubbles: true}})); }}"
                    args["js"] = js
                    await call_extension("page.evaluate", args)
                    return await call_extension("input.type", {"text": args.get("text", ""), "tabId": args.get("tabId")})
                elif name == "browser_submit":
                    is_css = args.get("_is_css", False)
                    sx = args['x'] if is_css else f"({args['x']} / 1000) * window.innerWidth"
                    sy = args['y'] if is_css else f"({args['y']} / 1000) * window.innerHeight"
                    js = f"let el = document.elementFromPoint({sx}, {sy}); if(el && el.form) {{ el.form.submit(); return true; }} return false;"
                    args["js"] = js
                    return await call_extension("page.evaluate", args)
            
            elif name == "browser_wait":
                import asyncio, time
                sel = args.get("selector", "")
                txt = args.get("text", "")
                timeout = args.get("timeout", 5000)
                start = time.time()
                while (time.time() - start) * 1000 < timeout:
                    snap = await call_extension("page.snapshot", args)
                    elements = snap.get("elements", [])
                    found = False
                    for el in elements:
                        if sel and (el.get("ref") == sel or el.get("tag") == sel): found = True
                        elif txt and txt.lower() in el.get("name", "").lower(): found = True
                    if found:
                        return {"found": True}
                    await asyncio.sleep(0.5)
                return {"found": False, "error": "timeout"}
                
            elif name in ("type", "browser_type"):
                text = args.get("text", "")
                if "x" in args and "y" in args:
                    is_css = args.get("_is_css", False)
                    sx = args['x'] if is_css else f"({args['x']} / 1000) * window.innerWidth"
                    sy = args['y'] if is_css else f"({args['y']} / 1000) * window.innerHeight"
                    js = f"let el = document.elementFromPoint({sx}, {sy}); if(el) el.focus();"
                    await call_extension("page.evaluate", {"js": js, "tabId": args.get("tabId")})
                if text.startswith("{") and text.endswith("}"):
                    key = text[1:-1]
                    return await call_extension("input.press_key", {"key": key, "tabId": args.get("tabId")})
                return await call_extension("input.type", args)
                    
        elif name == "browser_execute":
            act = args.get("action")
            p = args.get("params") or {}
            if "tabId" in args and "tabId" not in p: p["tabId"] = args["tabId"]
            if "tabId" in p and isinstance(p["tabId"], str) and p["tabId"].isdigit():
                p["tabId"] = int(p["tabId"])
            if act == "click": return await call_extension("input.click", p)
            if act == "type": return await call_extension("input.type", p)
            if act == "press_key": return await call_extension("input.press_key", p)
            if act == "navigate": return await call_extension("page.navigate", p)
            if act == "scroll": return await call_extension("input.scroll", p)
        raise RuntimeError(f"Command '{name}' is not supported by the Muse extension natively.")
        
    if pref.lower() == "csi":
        # External CSI Bridge (port 10088)
        if name in ("browser_tabs", "tabs_list"):
            return await call_csi("list_tabs", args)
        elif name == "browser_open":
            return await call_csi("navigate", args) # CSI overwrites active tab, it lacks a tab_create!
        elif name in ("tab_create", "tab_switch", "tab_close"):
            return {"ok": False, "error": f"CSI does not natively support {name}. Use backend: chrome for full tab management."}
        elif name in ("browser_model", "browser_find", "browser_extract"):
            # Map all extraction tools to snapshot
            snap = await call_csi("snapshot", args)
            return {"markdown": snap.get("tree", "")} if name == "browser_model" else snap
        elif name == "browser_execute":
            act = args.get("action")
            params = args.get("params") or {}
            if "tabId" in args and "tabId" not in params: params["tabId"] = args["tabId"]
            return await call_csi(act, params)
        elif name in ("click", "type", "navigate", "screenshot", "scroll", "browser_click", "browser_type", "browser_scroll", "browser_select", "browser_evaluate"):
            return await call_csi(name.replace("browser_", ""), args)
        raise RuntimeError(f"Command '{name}' is not supported by the CSI backend directly.")
            
    b = await router.resolve_backend(pref)

    # Fast paths that don't need a browser session at all
    import time
    if name == 'ping':
        return {'status': 'pong', 'time': time.time()}

    # Check if we actually need a tabId for this specific tool
    needs_tab = name in ("click", "type", "navigate", "screenshot", "browser_screenshot", "tab_switch", "tab_close", "browser_click", "browser_type", "browser_scroll", "browser_select", "browser_evaluate", "browser_execute", "browser_model", "browser_fill", "browser_submit", "browser_wait")
    
    tid = str(args.get("tabId") or "")

    if name.startswith("browser_") or name in ("click", "type", "navigate", "screenshot", "tabs_list", "tab_create", "tab_switch", "tab_close"):
        if not await b.is_connected():
            await b.start()
            
        if needs_tab and not tid:
            tabs = await b.list_tabs()
            if not tabs:
                await b.create_tab()
                tabs = await b.list_tabs()
            tid = str(tabs[0]["tabId"] if tabs else "")
    else:
        # Non-browser tools or tools that handle their own routing (like browser_task)
        pass



    # High-level task orchestration
    if name == "browser_task":
        import uuid
        task_id = str(args.get("taskId") or f"task-{uuid.uuid4().hex[:8]}")
        url = args.get("url")
        actions = args.get("actions", [])
        profile_name = args.get("profile") or profile_mgr.get_active_profile()

        # Risk assessment & approval gate
        risk = risk_engine.assess_risk("task", url or "", params={"actions": actions})
        if risk == ActionRiskLevel.CRITICAL and not args.get("approved"):
            task_engine.register_task(task_id, tool="browser_task", profile=profile_name, payload=args)
            task_engine.update_task(task_id, "waiting_approval", error="Critical risk task requires explicit approval")
            return {
                "taskId": task_id,
                "status": "waiting_approval",
                "risk": risk.value,
                "message": "Task paused. User approval required before execution.",
            }

        task = task_engine.register_task(task_id, tool="browser_task", profile=profile_name, payload=args)
        task_engine.update_task(task_id, "running")
        t0 = time.perf_counter()

        try:
            if profile_name == "csi":
                # Route directly to CSI daemon
                if url:
                    await call_csi("navigate", {"url": url})
                
                step_results = []
                for act in actions:
                    act_name = act.get("action")
                    if act_name == "click":
                        act_name = "mouse_click"
                    elif act_name == "type":
                        act_name = "key_type"
                    act_params = act.get("params", {})
                    if "text" in act_params and act_name == "mouse_click":
                        # csi click doesn't take text, we just pass what we have and let csi fail or succeed
                        pass
                        
                    res = await call_csi(act_name, act_params)
                    step_results.append(res)
                
                model_data = await call_csi("snapshot", {"mode": "compact"})
                dt_task = (time.perf_counter() - t0) * 1000.0
                task_engine.update_task(task_id, "completed", duration=dt_task)
                return {
                    "taskId": task_id,
                    "status": "completed",
                    "duration_ms": round(dt_task, 2),
                    "steps": step_results,
                    "page": {"type": "csi_snapshot", "data": model_data}
                }

            b_inst = await router.resolve_backend(BrowserBackendType.AUTO)
            if not await b_inst.is_connected():
                await b_inst.start()
            tabs_inst = await b_inst.list_tabs()
            cur_tid = tabs_inst[0]["tabId"] if tabs_inst else await b_inst.create_tab(url or "about:blank")
            if url and tabs_inst:
                await b_inst.navigate(cur_tid, url)

            # Barrier / CAPTCHA check
            captcha_info = await CaptchaDetector.detect(b_inst, cur_tid)
            if captcha_info.get("detected"):
                task_engine.update_task(task_id, "waiting_human", error=f"CAPTCHA: {captcha_info.get('type')}")
                return {
                    "taskId": task_id,
                    "status": "waiting_human",
                    "captcha": captcha_info,
                    "message": "Verification barrier detected. Please complete verification in browser.",
                }

            step_results = []
            for act in actions:
                act_name = act.get("action")
                act_params = act.get("params", {})
                res = await router.execute_action(cur_tid, act_name, act_params, backend=b_inst)
                step_results.append(res.to_dict())

            dt_task = (time.perf_counter() - t0) * 1000.0
            task_engine.update_task(task_id, "completed", duration=dt_task)
            model = await b_inst.build_page_model(cur_tid)
            return {
                "taskId": task_id,
                "status": "completed",
                "duration_ms": round(dt_task, 2),
                "steps": step_results,
                "page": model.to_compact_dict(),
            }
        except Exception as e:
            dt_task = (time.perf_counter() - t0) * 1000.0
            task_engine.update_task(task_id, "failed", error=str(e), duration=dt_task)
            return {"taskId": task_id, "status": "failed", "error": str(e), "duration_ms": round(dt_task, 2)}

    if name in ("browser_open", "navigate"):
        url = args.get("url", "about:blank")
        target_tid = str(args.get("tabId") or tid)
        if not target_tid:
            target_tid = await b.create_tab(url)
            ok = True
        else:
            ok = await b.navigate(target_tid, url)
        title = await b.get_title(target_tid)
        return {"ok": ok, "url": url, "title": title, "tabId": target_tid}

    if name == "browser_extract":
        if args.get("url"):
            res = await fetch_engine.fetch(args["url"], requirements=args.get("requirements"))
            return res.to_dict()
        model = await b.build_page_model(tid)
        fmt = args.get("format", "markdown")
        if fmt == "json":
            return model.to_dict()
        elif fmt == "compact":
            return model.to_compact_dict()
        return {"markdown": model.to_markdown()}

    if name in ("browser_click", "click"):
        if args.get("x") is not None and args.get("y") is not None:
            res = await router.execute_action(tid, "click", {"x": args["x"], "y": args["y"]}, backend=b)
            return res.to_dict()
        resolver = ElementResolver(cache=cache)
        q = ElementQuery(selector=args.get("selector"), name=args.get("text"))
        el = await resolver.resolve(b, tid, q)
        if not el:
            raise RuntimeError(f"Element not found: {args}")
        res = await router.execute_action(tid, "click", {"x": el.bounds.center_x, "y": el.bounds.center_y}, backend=b)
        return res.to_dict()

    if name in ("browser_type", "type"):
        res = await router.execute_action(tid, "type", {"text": args["text"]}, backend=b)
        return res.to_dict()

    if name == "browser_scroll":
        dy = 500 if args.get("direction", "down") == "down" else -500
        amount_val = args.get("amount") or args.get("deltaY") or args.get("delta_y") or args.get("y")
        if amount_val is not None:
            amount = int(amount_val)
            # If they provided an exact signed deltaY (e.g. -300), use it directly if direction isn't explicitly overriding
            if "direction" in args:
                dy = amount if args["direction"] == "down" else -amount
            else:
                dy = amount
        res = await router.execute_action(tid, "scroll", {"delta_x": int(args.get("deltaX", args.get("delta_x", args.get("x", 0)))), "delta_y": dy}, backend=b)
        return res.to_dict()

    if name in ("browser_screenshot", "screenshot"):
        raw = await b.screenshot(tid)
        import base64
        return {"bytes": len(raw), "base64": base64.b64encode(raw).decode()}

    if name in ("browser_tabs", "tabs_list"):
        act = args.get("action", "list")
        if act == "list" or name == "tabs_list":
            return await b.list_tabs()
        elif act == "switch":
            await b.switch_tab(args["tabId"])
            return {"switched": args["tabId"]}
        elif act == "create":
            new_id = await b.create_tab(args.get("url", "about:blank"))
            return {"tabId": new_id}
        elif act == "close":
            await b.close_tab(args.get("tabId") or tid)
            return {"closed": args.get("tabId") or tid}

    if name in ("browser_status", "browser_health"):
        st = await router.health_check()
        st["cache"] = cache.stats()
        st["ngrok"] = detect_ngrok_status()
        return st

    if name == "browser_task_status":
        t = task_engine.get_task(args.get("taskId", ""))
        return t.to_dict() if t else {"error": f"Task '{args.get('taskId')}' not found"}

    if name == "browser_task_cancel":
        ok = task_engine.cancel_task(args.get("taskId", ""))
        return {"cancelled": ok}

    if name in ("fetch_url", "fetch_extract"):
        res = await fetch_engine.fetch(
            url=args["url"],
            requirements=args.get("requirements"),
            options=args.get("options"),
        )
        return res.to_dict()

    if name == "tool_status":
        registry.detect_all()
        return [t.to_dict() for t in registry.list_tools()]

    if name == "tool_health":
        checks = await registry.check_all_health()
        doc = SystemDoctor.diagnose_system()
        return {"tools": {k: {"status": v[0].value, "detail": v[1]} for k, v in checks.items()}, "system": doc}

    # Computer Control Handlers
    if name == "computer_click":
        from core.tools.adapters.computer.pyautogui_adapter import PyAutoGUIAdapter
        comp = PyAutoGUIAdapter()
        res = await comp.mouse_click(int(args["x"]), int(args["y"]), button=args.get("button", "left"), clicks=int(args.get("clicks", 1)))
        return {"success": res.success, "action": res.action, "details": res.details, "error": res.error}

    if name == "computer_type":
        from core.tools.adapters.computer.pyautogui_adapter import PyAutoGUIAdapter
        comp = PyAutoGUIAdapter()
        res = await comp.type_text(args["text"])
        return {"success": res.success, "action": res.action, "details": res.details}

    if name == "computer_screenshot":
        import base64
        from core.tools.adapters.computer.pyautogui_adapter import PyAutoGUIAdapter
        comp = PyAutoGUIAdapter()
        png = await comp.take_screenshot()
        return {"format": "png", "base64": base64.b64encode(png).decode("utf-8")}

    if name == "computer_windows":
        from core.tools.adapters.computer.pyautogui_adapter import PyAutoGUIAdapter
        comp = PyAutoGUIAdapter()
        wins = await comp.list_windows()
        return [{"hwnd": w.hwnd, "title": w.title, "bounds": w.bounds} for w in wins]

    # Tool Management Handlers
    if name == "tools_install":
        from core.tools.installer import ToolInstaller
        t_name = args.get("tool_name", "")
        if t_name == "all":
            res = ToolInstaller.install_batch(registry.list_tools())
            return {k: {"success": v[0], "message": v[1]} for k, v in res.items()}
        tool = registry.get_tool(t_name)
        if not tool:
            return {"error": f"Tool '{t_name}' not found in registry"}
        ok, msg = ToolInstaller.install_tool(tool)
        return {"tool": t_name, "success": ok, "message": msg}

    if name == "tools_test":
        from core.tools.health import ToolHealthChecker
        t_name = args.get("tool_name", "")
        tool = registry.get_tool(t_name)
        if not tool:
            return {"error": f"Tool '{t_name}' not found"}
        res = await ToolHealthChecker.run_functional_contract(tool)
        return {"tool": t_name, **res}

    if name == "tools_benchmark":
        from core.tools.benchmark import ToolBenchmarker
        bm = ToolBenchmarker()
        t_name = args.get("tool_name", "http_static")
        cat = args.get("category", "browser")
        if cat == "computer" or "computer" in t_name:
            rep = await bm.benchmark_computer_tool(t_name)
        elif cat == "media" or t_name == "yt-dlp":
            rep = await bm.benchmark_media_tool(t_name)
        else:
            rep = await bm.benchmark_browser_tool(t_name)
        return rep.to_dict()

    if name == "tools_audit":
        from core.tools.auditor import ToolAuditor
        auditor = ToolAuditor()
        t_name = args.get("tool_name")
        tool = registry.get_tool(t_name) if t_name else None
        if tool:
            rep = auditor.audit_repository(tool.name, {"name": tool.display_name, "repository": tool.repo_url})
            return rep.to_dict()
        results = {}
        for t in registry.list_tools():
            rep = auditor.audit_repository(t.name, {"name": t.display_name, "repository": t.repo_url})
            results[t.name] = rep.to_dict()
        return results

    if name == "tools_configure":
        from core.tools.selector import ToolSelector
        sel = ToolSelector()
        cat = args.get("category")
        backend = args.get("backend")
        pref = args.get("preference")
        if cat and backend:
            sel.set_category_backend(cat, backend)
        if backend and pref:
            sel.set_tool_preference(backend, pref)
        return {"status": "configured", "preferences": sel.preferences}

    # Session Vault & Validation Handlers
    if name == "session_list":
        from core.session.vault import SessionVault
        v = SessionVault()
        records = v.list_sessions(domain=args.get("domain"))
        return [r.to_dict() for r in records]

    if name == "session_import":
        from core.session.importer import BrowserSessionImporter
        return BrowserSessionImporter.import_domain_session(
            browser_id=args.get("browser", "chrome"),
            profile_name=args.get("profile", "Default"),
            target_domains=args.get("domains", []),
            allowed_tools=args.get("allowed_tools"),
            session_name=args.get("name"),
        )

    if name == "session_validate":
        from core.session.vault import SessionVault
        from core.session.validator import SessionValidator
        v = SessionVault()
        sess_id = args.get("session_id", "")
        rec = v.get_session(sess_id)
        if not rec:
            return {"error": f"Session '{sess_id}' not found"}
        target_domain = args.get("domain") or (rec.domains[0] if rec.domains else "example.com")
        return await SessionValidator.validate_session_online(sess_id, target_domain, v)

    if name == "session_revoke":
        from core.session.vault import SessionVault
        v = SessionVault()
        sess_id = args.get("session_id", "")
        ok = v.revoke_session(sess_id)
        return {"session_id": sess_id, "revoked": ok}

    if name == "tools_validate":
        from core.validation.runner import ValidationRunner
        runner = ValidationRunner()
        return await runner.run_all()

    if name == "browser_model":
        model = await b.build_page_model(tid)
        fmt = args.get("format", "markdown")
        if fmt == "json":
            return model.to_dict()
        elif fmt == "compact":
            return model.to_compact_dict()
        return {"markdown": model.to_markdown()}

    if name in ("browser_evaluate", "evaluate"):
        if hasattr(b, "evaluate"):
            return await b.evaluate(tid, args.get("js", ""))
        raise RuntimeError(f"Backend {b.backend_type().name} does not support evaluate")

    if name in ("select", "browser_select"):
        if hasattr(b, "evaluate"):
            val = args.get("value", "").replace("'", "\'")
            is_css = args.get("_is_css", False)
            sx = args['x'] if is_css else f"({args['x']} / 1000) * window.innerWidth"
            sy = args['y'] if is_css else f"({args['y']} / 1000) * window.innerHeight"
            js = f"(() => {{ let el = document.elementFromPoint({sx}, {sy}); if(el){{ el.value = '{val}'; el.dispatchEvent(new Event('change', {{bubbles: true}})); return el.value; }} return null; }})()"
            return await b.evaluate(tid, js)
        raise RuntimeError(f"Backend {b.backend_type().name} does not support evaluate")

    if name == "browser_find":
        resolver = ElementResolver(cache=cache)
        q = ElementQuery(
            description=args.get("query"),
            name=args.get("query") or args.get("text"),
            role=args.get("role"),
            selector=args.get("selector"),
            text=args.get("text"),
        )
        el = await resolver.resolve(b, tid, q)
        return {"found": bool(el), "elements": [el.to_dict()] if el else []}

    if name == "browser_execute":
        act = args["action"]
        params = args.get("params") or {}
        res = await router.execute_action(
            tab_id=tid,
            action=act,
            params=params,
            verify=args.get("verify", True),
            backend=b,
        )
        return res.to_dict()

    if name == "browser_detect_captcha":
        return await CaptchaDetector.detect(b, tid)

    if name == "tab_switch":
        await b.switch_tab(args["tabId"], focus=bool(args.get("focus")))
        return {"switched": args["tabId"]}

    if name == "tab_create":
        new_id = await b.create_tab(args.get("url", "about:blank"))
        return {"tabId": new_id}

    if name == "tab_close":
        target = args.get("tabId") or tid
        await b.close_tab(target)
        return {"closed": target}

    # Fallback to extension bridge if connected
    res = await call_extension(name, args)
    if not res.get("ok"):
        raise RuntimeError(res.get("error", f"Tool {name} failed"))
    return res.get("result")


async def handle_mcp_post(request: web.Request) -> web.Response:
    """Handle MCP JSON-RPC 2.0 requests over HTTP."""
    if not verify_auth(request):
        return web.json_response({"jsonrpc": "2.0", "error": {"code": -32000, "message": "unauthorized"}}, status=401)

    try:
        req = await request.json()
    except Exception:
        return web.json_response({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}}, status=400)

    method = req.get("method")
    rid = req.get("id")

    from core.exposure.security import PublicSecurityPolicy
    policy = PublicSecurityPolicy()
    is_public = policy.is_public_request(dict(request.headers), request.remote)

    if method == "initialize":
        return web.json_response({
            "jsonrpc": "2.0",
            "id": rid,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}, "logging": {}},
                "serverInfo": {"name": "muse-browser", "version": "4.0.0"},
            },
        })

    if method == "ping":
        return web.json_response({"jsonrpc": "2.0", "id": rid, "result": {}})

    if method == "tools/list":
        if is_public:
            filtered = [t for t in MCP_TOOLS if policy.is_tool_allowed(t["name"], is_public=True)[0]]
            return web.json_response({"jsonrpc": "2.0", "id": rid, "result": {"tools": filtered}})
        return web.json_response({"jsonrpc": "2.0", "id": rid, "result": {"tools": MCP_TOOLS}})

    if method == "tools/call":
        params = req.get("params", {})
        t_name = params.get("name", "")
        t_args = params.get("arguments", {})

        allowed, err_msg = policy.is_tool_allowed(t_name, is_public=is_public)
        if not allowed:
            return web.json_response({
                "jsonrpc": "2.0",
                "id": rid,
                "result": {"content": [{"type": "text", "text": f"Security Error: {err_msg}"}], "isError": True},
            })

        try:
            val = await dispatch_tool_call(t_name, t_args)
            return web.json_response({
                "jsonrpc": "2.0",
                "id": rid,
                "result": {"content": [{"type": "text", "text": json.dumps(val, indent=2)}]},
            })
        except Exception as exc:
            return web.json_response({
                "jsonrpc": "2.0",
                "id": rid,
                "result": {"content": [{"type": "text", "text": f"Error: {exc}"}], "isError": True},
            })

    return web.json_response({
        "jsonrpc": "2.0",
        "id": rid,
        "error": {"code": -32601, "message": f"Method '{method}' not found"},
    })


async def handle_exposure_status(request: web.Request) -> web.Response:
    from core.exposure.manager import ExposureManager
    mgr = ExposureManager()
    return web.json_response({"ok": True, "result": mgr.get_status(is_self=True)})


async def handle_exposure_mode(request: web.Request) -> web.Response:
    from core.exposure.manager import ExposureManager, ExposureMode
    mgr = ExposureManager()
    try:
        body = await request.json()
    except Exception:
        body = {}
    target_mode = body.get("mode", "local")
    try:
        emode = ExposureMode(target_mode.lower())
        res = mgr.set_mode(emode, is_self=True)
        if "error" in res:
            return web.json_response({"ok": False, "error": res["error"]}, status=400)
        return web.json_response({"ok": True, "result": res})
    except ValueError:
        return web.json_response({"ok": False, "error": f"Invalid mode '{target_mode}'"}, status=400)


async def handle_mcp_sse(request: web.Request) -> web.StreamResponse:
    """Handle MCP SSE transport for streaming MCP clients."""
    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )
    await response.prepare(request)
    endpoint_uri = f"/mcp"
    await response.write(f"event: endpoint\ndata: {endpoint_uri}\n\n".encode("utf-8"))
    try:
        while True:
            await asyncio.sleep(10.0)
            await response.write(b": ping\n\n")
    except asyncio.CancelledError:
        pass
    return response


# ---------------- REST Browser API on /api/browser/... ----------------

async def handle_browser_api(request: web.Request) -> web.Response:
    if not verify_auth(request):
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)

    endpoint = request.match_info.get("endpoint", "")
    method = request.method

    try:
        body: Dict[str, Any] = {}
        if method == "POST":
            try:
                body = await request.json()
            except Exception:
                pass

        if endpoint == "status":
            st = await router.health_check()
            st["cache"] = cache.stats()
            st["ngrok"] = detect_ngrok_status()
            return web.json_response({"ok": True, "result": st})

        if endpoint == "tabs":
            pref = body.get('backend', 'auto') if isinstance(body, dict) else 'auto'
            b = await router.resolve_backend(pref)
            if not await b.is_connected():
                await b.start()
            tabs = await b.list_tabs()
            return web.json_response({"ok": True, "result": tabs})

        if endpoint == "model":
            pref = body.get('backend', 'auto') if isinstance(body, dict) else 'auto'
            b = await router.resolve_backend(pref)
            tabs = await b.list_tabs()
            tid = str(body.get("tabId") or (tabs[0]["tabId"] if tabs else ""))
            model = await b.build_page_model(tid)
            fmt = body.get("format", "compact")
            if fmt == "markdown":
                return web.json_response({"ok": True, "result": model.to_markdown()})
            elif fmt == "json":
                return web.json_response({"ok": True, "result": model.to_dict()})
            return web.json_response({"ok": True, "result": model.to_compact_dict()})

        if endpoint == "execute":
            pref = body.get('backend', 'auto') if isinstance(body, dict) else 'auto'
            b = await router.resolve_backend(pref)
            tabs = await b.list_tabs()
            tid = str(body.get("tabId") or (tabs[0]["tabId"] if tabs else ""))
            act_res = await router.execute_action(
                tab_id=tid,
                action=body.get("action", "click"),
                params=body.get("params"),
                verify=body.get("verify", True),
                backend=b,
            )
            return web.json_response({"ok": act_res.ok, "result": act_res.to_dict()})

        if endpoint == "find":
            pref = body.get('backend', 'auto') if isinstance(body, dict) else 'auto'
            b = await router.resolve_backend(pref)
            tabs = await b.list_tabs()
            tid = str(body.get("tabId") or (tabs[0]["tabId"] if tabs else ""))
            resolver = ElementResolver(cache=cache)
            q = ElementQuery(
                selector=body.get("selector"),
                name=body.get("name") or body.get("text"),
                role=body.get("role"),
            )
            el = await resolver.resolve(b, tid, q)
            return web.json_response({"ok": bool(el), "element": el.to_dict() if el else None})

        if endpoint == "traces":
            return web.json_response(tracer.get_recent(50))

        if endpoint == "workspaces":
            return web.json_response({"ok": True, "workspaces": pool.list_workspaces()})

        return web.json_response({"ok": False, "error": f"Unknown browser endpoint: {endpoint}"}, status=404)
    except Exception as exc:
        logger.exception("Error in browser API endpoint /api/browser/%s", endpoint)
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def handle_legacy_tool(request: web.Request) -> web.Response:
    """Backward compatibility for legacy simpled POST /tool callers."""
    if not verify_auth(request):
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
    try:
        data = await request.json()
    except Exception:
        data = {}
    tool = data.get("tool", "")
    args = data.get("args", {})
    try:
        val = await dispatch_tool_call(tool, args)
        return web.json_response({"ok": True, "result": val})
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)})


def create_app() -> web.Application:
    app = web.Application()

    # CORS options
    async def handle_options(request):
        return web.Response(
            status=204,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Muse-Token",
            },
        )

    # Routes multiplexed on 18010
    app.router.add_route("OPTIONS", "/{tail:.*}", handle_options)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/status", handle_health)
    app.router.add_get("/dashboard", handle_dashboard)
    app.router.add_get("/", handle_dashboard)
    app.router.add_get("/events", handle_events_sse)
    app.router.add_get("/ws", handle_ws)
    app.router.add_post("/mcp", handle_mcp_post)
    app.router.add_get("/mcp", handle_mcp_sse)
    app.router.add_get("/api/browser/{endpoint}", handle_browser_api)
    app.router.add_post("/api/browser/{endpoint}", handle_browser_api)
    app.router.add_get("/api/exposure/status", handle_exposure_status)
    app.router.add_post("/api/exposure/mode", handle_exposure_mode)
    app.router.add_post("/tool", handle_legacy_tool)

    return app


async def main() -> None:
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HTTP_HOST, HTTP_PORT)
    await site.start()
    print(f"============================================================", flush=True)
    print(f"Muse Browser Automation 3.0 Unified Single-Port Server", flush=True)
    print(f"Local URL   : http://{HTTP_HOST}:{HTTP_PORT}", flush=True)
    print(f"MCP URL     : http://{HTTP_HOST}:{HTTP_PORT}/mcp", flush=True)
    print(f"WebSocket   : ws://{HTTP_HOST}:{HTTP_PORT}/ws", flush=True)
    print(f"Dashboard   : http://{HTTP_HOST}:{HTTP_PORT}/dashboard", flush=True)
    print(f"Health      : http://{HTTP_HOST}:{HTTP_PORT}/health", flush=True)
    print(f"============================================================", flush=True)

    # Keep server running
    try:
        await asyncio.Future()
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
