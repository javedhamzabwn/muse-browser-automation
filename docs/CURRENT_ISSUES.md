# Current Issues & Technical Limitations — Muse Browser Automation 2.x

## 1. Architectural & Protocol Issues

1. **Dual Control Planes Without Shared State**:
   - `simpled.py` (HTTP) and `mcp_server.py` (MCP stdio) are separate processes. While `mcp_server.py` now detects `simpled.py` on port 18010, they do not share unified task history, metrics, or connection pools.
2. **Obscura Engine Isolated from MCP**:
   - Obscura is driven exclusively by `obscura/obscura_helper.py` and `obscura/profiles.py`. It is **not** exposed to the MCP server or the HTTP daemon `/tool` endpoint. The agent cannot use Obscura through MCP without writing custom Python scripts.
3. **No Central Browser Router**:
   - No mechanism exists for `browser="auto"`. Routing between personal Chrome, Obscura, and other local engines (e.g. Playwright, Camoufox) is completely manual.

---

## 2. Element Resolution & DOM Interaction Flaws

1. **Fragility of Snapshot References (`ref: e0`)**:
   - The snapshot generates sequential refs (`e0`, `e1`, `e2`...) based on current DOM order.
   - Any dynamic page update (e.g. a live banner, toast, dropdown, React state update) shifts all references immediately, causing clicks on the wrong element or invalid coordinates.
2. **Viewport Clipping Bug in Snapshot**:
   - `SNAPSHOT_JS` ignores elements whose top/bottom are outside the current viewport (`r.bottom < 0 || r.top > window.innerHeight`).
   - Elements below the fold cannot be identified or clicked without manual exploratory scrolling.
3. **No Shadow DOM or Iframe Penetration**:
   - `document.querySelectorAll()` in `SNAPSHOT_JS` does not traverse `shadowRoot` (Web Components) or `iframe` documents.
   - Sites using modern frameworks (Salesforce, Shopify, Web Components, payment iframes) are partially or completely invisible to the agent.
4. **No Semantic or Accessibility Tree Integration**:
   - Current system knows nothing about the accessibility tree (`AXNode`), ARIA role hierarchies, or semantic text relationships. It only matches basic HTML tags and coarse attributes.

---

## 3. Reliability & Timing Issues

1. **Fixed Sleep Statements**:
   - `mcp_server.py` waits `asyncio.sleep(0.8)` after every click.
   - `obscura_helper.py` waits `asyncio.sleep(3)` after navigation.
   - Causes sluggish operation on fast sites, and causes race conditions / premature timeouts on slow sites.
2. **Dialogs & Popups Block Automation**:
   - Standard browser dialogs (`window.alert`, `window.confirm`, `window.prompt`, `beforeunload`) freeze CDP until handled. Current extension has no auto-dialog handler.
   - Modals and cookie consent popups intercept pointer events, causing CDP mouse clicks to land on overlays rather than intended targets.
3. **Lack of Human-in-the-Loop Safeguards**:
   - No detection for Cloudflare Turnstile, reCAPTCHA, hCaptcha, 2FA prompts, or banking confirmations. When encountering these, the agent either stalls or risks lockouts.

---

## 4. Security & Safety

1. **Zero-Authentication Loopback Exposure**:
   - `simpled.py` binds to `127.0.0.1:18010` without mandatory authentication by default.
   - Any local software or compromised script on the machine can issue `POST /tool` calls and dump all Chrome cookies via `cookies.export_cdp`.
2. **No Dry-Run or Risk Engine**:
   - Destruction actions (delete, unenroll, transfer, post, purchase) have the exact same execution path as read-only operations.

---

## 5. Engineering & Infrastructure Debt

1. **Complete Absence of Automated Tests**:
   - The repository contains zero unit, integration, or performance tests.
2. **No Central Logging or Observability**:
   - Logs are output to stdout/stderr; no structured JSON event log, no historical task tracing, and no `/dashboard` endpoint.
3. **No Self-Healing or Selector Memory**:
   - Every single task rediscovers the DOM from zero. No database or cache remembers working selectors or page patterns.
