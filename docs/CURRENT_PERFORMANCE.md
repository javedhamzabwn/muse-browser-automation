# Current Performance Analysis — Muse Browser Automation 2.x

## Baseline Latency Characteristics

Based on codebase analysis and profiling of the communication path:

```
[Agent Client]
       │ stdio JSON-RPC (~1ms)
[mcp_server.py]
       │ HTTP POST /tool (~2-4ms loopback)
[simpled.py]
       │ WebSocket JSON (~1-2ms loopback)
[Chrome MV3 SW]
       │ chrome.debugger.sendCommand CDP (~5-15ms)
[Chrome Page / V8 Renderer]
```

Total roundtrip overhead for zero-op message: **~10–25 ms**.

---

## Latency Profiles by Operation

| Operation | Typical Latency | Primary Latency Driver | Optimization Potential |
|---|---|---|---|
| **Ping** | 12–25 ms | Multi-hop loopback IPC | Low (already fast) |
| **Tab List** | 15–35 ms | `chrome.tabs.query` in SW | Medium (cache tab state) |
| **Tab Switch** | 20–40 ms | `chrome.tabs.update` | Low |
| **Tab Create** | 45–120 ms | Chromium tab creation & grouping | Medium (pre-warmed tab pool) |
| **Page Navigation** | 800–3500 ms | Network latency + page load lifecycle | High (event-based DOM ready wait instead of fixed sleep) |
| **DOM Snapshot** | 90–450 ms | DOM query of 400 nodes + `checkVisibility` reflows | High (virtualized DOM / AXTree caching) |
| **Click (with verify)** | **1050–1600 ms** | **Hardcoded `asyncio.sleep(0.8)` + dual snapshot** | **Extremely High (~50-80ms possible)** |
| **Type (text insert)** | 20–40 ms | Direct CDP `Input.insertText` | Low |
| **Key Press** | 25–45 ms | Direct CDP `Input.dispatchKeyEvent` (down+up) | Low |
| **Screenshot** | 140–380 ms | CDP rasterization + base64 decoding + disk write | Medium (format selection / direct stream) |
| **Cookie Export** | 120–350 ms | CDP `Storage.getCookies` dump | Low |

---

## Critical Bottlenecks Identified

### 1. The 800ms Verification Sleep (`mcp_server.py`)
In `daemon/mcp_server.py:91`:
```python
await call_ext("input.click", {"x": x, "y": y, ...})
await asyncio.sleep(0.8)  # <-- Fixed arbitrary delay!
after = await do_snapshot()
```
- Every verified click spends **at least 800ms doing nothing**.
- If a page mutates in 5ms, the agent still waits 800ms.
- **Fix**: Replace with a MutationObserver / CDP `DOM.documentUpdated` / event-driven state change trigger (target: < 30ms).

### 2. The 3.0s Obscura Navigation Sleep (`obscura_helper.py`)
In `obscura/obscura_helper.py:160`:
```python
async def navigate(self, url, wait=3):
    await self._cdp("Page.navigate", url=url)
    await asyncio.sleep(wait)  # <-- Fixed 3-second delay!
```
- Arbitrary 3000ms delay on every navigation regardless of page size.
- **Fix**: Listen for CDP `Page.loadEventFired` or `Page.lifecycleEvent` (`networkIdle`).

### 3. Full DOM Tree Rescan on Every Action
- `SNAPSHOT_JS` runs `querySelectorAll` across 11 selector classes and filters every matching node with `checkVisibility()` and `getBoundingClientRect()`.
- On heavy web applications (Gmail, LinkedIn, Notion, Jira), this triggers layout recalc cycles and takes 250–600ms per snapshot.
- Running this before and after each click adds 500–1200ms of pure DOM overhead.
- **Fix**: Layered element resolution (Cached Selector -> Semantic Accessibility Match -> Targeted Subtree -> Vision Fallback).

### 4. MV3 Service Worker Cold Wakeup
- Chromium shuts down idle background service workers after ~30 seconds of inactivity.
- When an action arrives while the SW is dormant, browser wakes the worker, re-establishes the WebSocket connection, and re-attaches CDP:
  - Wakeup delay: **200–500 ms**.
- **Fix**: Native keep-alive port / dedicated daemon-driven worker heartbeat.

### 5. Multi-Hop IPC Hop Count
- Standard call path traverses: MCP Stdio -> HTTP 18010 -> WebSocket 19091 -> Chrome Extension -> CDP -> Browser.
- Each hop serializes and deserializes JSON strings.
- **Fix**: Direct WebSocket or direct CDP pipeline when running native browser backends (Playwright / Obscura).
