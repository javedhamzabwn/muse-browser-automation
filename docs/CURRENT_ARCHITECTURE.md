# Current Architecture — Muse Browser Automation 2.x

## System Overview

Muse Browser Automation 2.x is a dual-browser automation stack designed for Windows local environments, targeting loopback agent control without window focus-stealing.

```
                    AI Agent / MCP Client
                              │
                    ┌─────────┴─────────┐
                    │ stdio (JSON-RPC)  │
                    ▼                   ▼
          mcp_server.py (MCP)   simpled.py (HTTP :18010)
                    │                   │
                    └─────────┬─────────┘
                              │ ws://127.0.0.1:19091
                              ▼
                 MV3 Chrome Extension (Worker)
                    │ (chrome.debugger CDP)
                    ▼
          ┌───────────────────────────────────┐
          │ Personal Chrome (Background Tabs) │
          │ Tab Group: "Muse automation"      │
          └───────────────────────────────────┘

         Separate Out-of-Process Sidecar:
          ┌───────────────────────────────────┐
          │ Obscura Browser (Rust Engine)     │
          │ CDP Port :9222 (--stealth)        │
          └─────────────────┬─────────────────┘
                            │ CDP ws://127.0.0.1:9222
                            ▼
          obscura_helper.py / profiles.py
```

## Component Architecture

### 1. Chrome MV3 Extension (`extension/`)
- **Technology**: Manifest V3 Service Worker (`background.js`).
- **Permissions**: `debugger`, `tabs`, `activeTab`, `scripting`, `storage`, `alarms`, `tabGroups`, `bookmarks`, `<all_urls>`.
- **Communication**: Outbound WebSocket connection to `ws://127.0.0.1:19091`. Reconnects via `chrome.alarms` and tab/window activity listeners.
- **CDP Engine**: Uses `chrome.debugger.attach` with CDP version 1.3.
- **Isolation Boundary**: Tab Group `"Muse automation"` prevents interacting with user personal tabs. Fallback to `chrome.storage.local` (`muse_auto_tabs`) when `tabGroups` API is unavailable.
- **Viewport Normalization**: Overrides device metrics to `1280x800` on attach to prevent background tab 0x0 viewport layout/screenshot crashes.
- **Session Recovery**: State stored in `chrome.storage.local` (`muse_sessions`); automatically attempts to recreate closed session tabs if marked active.

### 2. Daemon Bridge (`daemon/simpled.py`)
- **HTTP Server**: Listens on `127.0.0.1:18010`. Endpoints:
  - `GET /health`: Extension connected state.
  - `POST /tool`: Dispatches tool requests via `TOOL_MAP`.
- **WebSocket Server**: Listens on `127.0.0.1:19091`. Bridges HTTP requests to extension messages using thread-safe `concurrent.futures.Future` with sequential request IDs.
- **Security**: Bound to `127.0.0.1`. Optional token authentication (`MUSE_AUTH_TOKEN`).

### 3. MCP Server (`daemon/mcp_server.py`)
- **Protocol**: MCP stdio JSON-RPC (`initialize`, `tools/list`, `tools/call`, `ping`).
- **Connection Modes**:
  - **Daemon Proxy Mode**: If `simpled.py` is listening on `127.0.0.1:18010`, forwards calls over HTTP.
  - **Standalone Mode**: If `simpled.py` is not running, binds WebSocket directly on `127.0.0.1:19091`.
- **Image Handling**: Disk caching for screenshots under `~/muse-browser-mcp/shots/` to prevent large base64 payload overflow.

### 4. Obscura Stealth Engine (`obscura/`)
- **Engine**: Independent Rust browser engine (upstream `h4ckf0r0day/obscura`), embedded V8, native layout and paint.
- **Control Interface**: Native CDP on port `9222` (default). Driven by `obscura_helper.py` via `Target.createTarget` and `Target.attachToTarget` with `flatten=True`.
- **Script Execution**: Evaluates JavaScript wrapped in arrow-function IIFEs `(() => { ... })()` due to parser quirks with anonymous functions.
- **Profile Manager (`profiles.py`)**: Subcommands for `main` (persistent), `temp` (cloned cookies, disposable), `empty` (clean slate), `sync` (cookie ingestion), `list`, `cleanup`.

### 5. Cookie Synchronization Pipeline (`tools/export_cookies.py`)
- Extracts full cookie jar from Chrome without manifest permissions using CDP `Storage.getCookies` via the extension debugger.
- Converts raw CDP cookies to Netscape `cookies.txt` format.
- Output path: `%USERPROFILE%\Downloads\cookies-export.txt`.
- `profiles.py sync` merges `cookies-export.txt` into Obscura profile's `cookies.json` on disk and restarts Obscura.

### 6. Deployment & Autostart (`install/`)
- `install.ps1`: Deploys codebase to `%USERPROFILE%\muse-browser-mcp`, installs dependencies (`websockets`), registers VBS startup script, schedules daily cookie dump task.
- `StartMuseMCP.vbs`: Launches `pythonw.exe simpled.py` hidden at user login.
