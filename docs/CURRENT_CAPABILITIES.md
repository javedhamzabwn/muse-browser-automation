# Current Capabilities — Muse Browser Automation 2.x

## Implemented Features

### 1. Tab Management
- `tabs_list` (`tabs.list`): Lists tabs strictly within `"Muse automation"` tab group or tracked in `muse_auto_tabs`.
- `tab_switch` (`tabs.switch`): Switches active tab in Chrome without raising or focusing the desktop window unless `{ focus: true }`.
- `tab_create` (`tabs.create`): Opens a new tab in the background and places it in the `"Muse automation"` group.
- `tab_close` (`tabs.close`): Closes specified automation tab and unregisters from active session tracking.
- `tab_group` (`tabs.group`): Groups specified tab IDs under `"Muse automation"` (blue group tag).
- `tab_cleanup` (`tabs.cleanup`): Closes empty / `about:blank` / `chrome://newtab/` tabs in the automation group.
- `tab_adopt` (`tabs.adopt`): Adopts active or specified tab into the automation group.
- `session_start` / `session_end` / `session_recover`: Multi-tab session tracking surviving service worker restarts; automatically reopens tabs closed mid-automation.

### 2. Browser Inspection & DOM Extraction
- `snapshot` (`page.snapshot`):
  - Injected script `SNAPSHOT_JS` runs via `Runtime.evaluate`.
  - Queries interactive tags: `a, button, input, select, textarea, [role=...], [onclick], [tabindex]`.
  - Filters non-visible elements via `checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })`.
  - Extracts center coordinate `(x, y)`, dimensions `(w, h)`, tag, type, role, and text label (up to 400 elements).
- `page.title` / `page.url`: Fast string lookups for current tab title and URL.
- `screenshot` (`page.screenshot`): Takes PNG capture via CDP `Page.captureScreenshot` (`captureBeyondViewport: true`). Writes to disk under `~/muse-browser-mcp/shots/`.

### 3. Visual Grounding (Set-of-Marks)
- `som_mark` (`page.som_mark`): Injects numbered high-contrast black badges (0..199) over clickable DOM elements for vision/coordinate targeting.
- `som_clear` (`page.som_clear`): Removes injected mark DOM nodes (`.muse-som-mark`).

### 4. Input Emulation
- `click` (`input.click`): Dispatches CDP `Input.dispatchMouseEvent` (`mouseMoved`, `mousePressed`, `mouseReleased`).
  - Supports clicking by `(x, y)` coordinate or `ref` (from snapshot).
  - Built-in verification in MCP server: compares before/after URL, title, and interactive element count.
- `type` (`input.type`): Dispatches CDP `Input.insertText`.
- `press_key` (`input.press_key`): Dispatches CDP `Input.dispatchKeyEvent` with virtual key codes for navigation keys (`Enter`, `Tab`, `Escape`, `Backspace`, `Delete`, arrows, `Home`, `End`, `PageUp`, `PageDown`) or text insertion for single characters.
- `scroll` (`input.scroll`): Dispatches CDP `Input.dispatchMouseEvent` `mouseWheel`.

### 5. Navigation & Scripting
- `navigate` (`page.navigate`): Calls CDP `Page.navigate`.
- `go_back` (`page.back`): Executes `history.back()`.
- `go_forward` (`page.forward`): Executes `history.forward()`.
- `evaluate` (`page.evaluate`): Evaluates arbitrary JavaScript inside an async IIFE wrapper.

### 6. Bookmark API
- `bookmarks_tree` (`bookmarks.tree`): Reads Chrome bookmark hierarchy directly through `chrome.bookmarks.getTree()` without opening `chrome://bookmarks` UI.
- `bookmarks_search` (`bookmarks.search`): Filters bookmarks by text query.

### 7. Cookie Management
- `cookies_export` (`cookies.export_cdp`): Queries Chrome's full cookie jar via CDP `Storage.getCookies` without needing the `cookies` extension permission.
- `tools/export_cookies.py`: Exports Netscape format `cookies-export.txt` to Downloads.
- `obscura/profiles.py sync`: Merges Netscape / CDP cookies into Obscura profile's `cookies.json`.

---

## Missing & Gap Analysis (Against 3.0 Goals)

| Requirement | Current Status | Limitation in 2.x |
|---|---|---|
| **Unified Browser Router** | Missing | Chrome and Obscura are isolated, requiring separate manual scripts (`simpled.py` vs `obscura_helper.py`). |
| **Semantic Element Resolver** | Missing | Relies entirely on brittle snapshot element index (`ref: e0`) or raw `(x, y)` pixel coordinates. |
| **Accessibility Tree Resolution** | Missing | Does not query CDP Accessibility tree (`Accessibility.getFullAXTree`), only basic DOM selector. |
| **Shadow DOM & Iframe Traversal** | Missing | Snapshot selector cannot penetrate open/closed Shadow DOM or cross-origin iframes. |
| **Element & Workflow Cache** | Missing | Every operation requires re-extracting snapshot from scratch. Zero reuse of learned selectors. |
| **Self-Healing Selectors** | Missing | If DOM shifts or ref fails, throws error; no alternate selector search. |
| **Event-Driven Waits** | Missing | Uses fixed sleeps (`asyncio.sleep(0.8)`) instead of DOM mutation or network idle observers. |
| **Resource Governor & Browser Pool**| Missing | No worker pooling or concurrency caps. |
| **Task Engine & Checkpoints** | Missing | Tasks cannot be paused, resumed, or persisted across restarts. |
| **Multi-tab Workspaces** | Missing | Only supports a single flat tab group `"Muse automation"`. |
| **Human-in-the-Loop & Risk Engine** | Missing | No CAPTCHA/2FA detection, no dry-run mode, no action permission checks. |
| **Structured Extraction Engine** | Missing | No schema-driven extraction for products, tables, or unstructured text. |
| **Dashboard & Observability** | Missing | No web dashboard or event stream on `:18010/dashboard`. |
