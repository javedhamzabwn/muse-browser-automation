# Architecture

`muse-browser-automation` drives a real desktop browser locally on the
user's PC. Everything runs on loopback; the agent's brain (Muse) talks to
the PC over the user's own tunnel, but **no browsing traffic or control
plane ever leaves the machine except through a tunnel the user sets up
themselves**.

## Component diagram

```
Chrome (personal)                          Obscura (agent browser, default)
┌─────────────────────────┐                ┌──────────────────────────────┐
│ MV3 extension           │                │ from-scratch Rust engine   │
│ "Muse Browser Control"  │                │ (not Chromium)             │
│ background service      │                │ CDP :9222                  │
│ worker: debugger        │                └──────────────┬───────────────┘
│ permission, CDP on      │                               │ obscura_helper.py
│ BACKGROUND tabs         │                               │ profiles.py
│ (no-focus automation)   │                               │
└────────────┬────────────┘                               │
             │ WS 127.0.0.1:19091                         │
             ▼                                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ simpled.py — loopback daemon                                    │
│   HTTP 127.0.0.1:18010  POST /tool  {"tool": dotted.name, ...}  │
│   WebSocket 127.0.0.1:19091  (extension <-> daemon bridge)      │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────┐
│ mcp_server.py — MCP     │
│ server exposing daemon  │
│ tools to the agent      │
└─────────────────────────┘
```

Dotted tool names (e.g. `cookies.export_cdp`, `tabs.snapshot`) are called
over HTTP `/tool`; the daemon relays browser work to the extension over
the WebSocket. The extension uses the `debugger` permission to drive tabs
via CDP (`Input.dispatchMouseEvent`, `Runtime.evaluate`,
`Page.captureScreenshot`) **without activating them** — automation never
steals window focus.

## Key files

| File | Role |
|------|------|
| `extension/manifest.json`, `extension/background.js` | MV3 extension, debugger permission, background-tab CDP |
| `daemon/simpled.py` | loopback daemon: HTTP `:18010` `/tool` + WS `:19091` |
| `daemon/mcp_server.py` | MCP server fronting the daemon for agents |
| `install/StartMuseMCP.vbs` | login autostart for the daemon (generic, no hardcoded paths) |
| `install/install.ps1` | idempotent Windows installer |
| `tools/export_cookies.py` | daily CDP cookie export → `Downloads/cookies-export.txt` (Netscape) |
| `obscura/obscura_helper.py` | CDP driver for Obscura (`:9222`) |
| `obscura/profiles.py` | Obscura profile manager (main/temp/empty/sync/list/cleanup) |

## Ports (all 127.0.0.1, loopback-only)

| Port | Service |
|------|---------|
| 18010 | daemon HTTP `/tool` (dotted method names) |
| 19091 | daemon WebSocket (extension bridge) |
| 9222  | Obscura CDP (main profile) |

## Trust boundaries

- The daemon binds loopback only and performs no auth — it trusts the local
  machine. **Never port-forward these ports publicly** without adding
  authentication in front of them.
- The extension's `<all_urls>` + `debugger` permissions are powerful by
  design: only load it from this repo, and only on a machine you control.
- Cookie exports (`cookies-export.txt`) are session credentials — they stay
  in the user's Downloads folder and are never uploaded anywhere by these
  tools.
