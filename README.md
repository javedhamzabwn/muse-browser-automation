# muse-browser-automation

A complete, self-installing browser-automation stack for a Windows PC: a
custom Chrome extension, a loopback control daemon, an MCP server, and an
Obscura sidecar setup — plus a **paste-ready setup prompt** (`SETUP_PROMPT.md`)
so anyone can get an AI agent to install the whole thing by itself.

## The 30-second version

1. Paste the repo link + the prompt from `SETUP_PROMPT.md` into your AI agent.
2. The agent installs everything through the terminal by itself.
3. You do one 4-click step in Chrome (load the unpacked extension) and,
   optionally, hand over your ngrok authtoken for remote access.
4. The agent proves it works and says **AUTOMATION READY**.

## What's inside

| Path | What it is |
|---|---|
| `extension/` | Custom Chrome MV3 extension — **Muse Browser Control v1.2.1**. Drives background tabs via CDP (never steals window focus), reads the full cookie jar via the debugger permission, bookmarks via the bookmarks API. |
| `daemon/` | `simpled.py` — loopback daemon: HTTP `127.0.0.1:18010` `/tool` (dotted method names) + WebSocket `127.0.0.1:19091` for the extension. `mcp_server.py` — MCP server front-end. |
| `obscura/` | The **Obscura section**: `obscura_helper.py` (drive Obscura over CDP), `profiles.py` (main/temp/empty/sync profile manager), and setup docs. Obscura itself is downloaded from upstream, never vendored. |
| `tools/` | `export_cookies.py` — daily cookie export (Netscape format) for session sync; runs via Scheduled Task at 04:00. |
| `install/` | `install.ps1` — one-command Windows installer. `StartMuseMCP.vbs` — daemon auto-start on login. |
| `docs/` | `ARCHITECTURE.md` — how the pieces fit. |
| `SETUP_PROMPT.md` | **The prompt.** Paste it + the repo link into an agent and it sets everything up. |

## Two browsers, on purpose

- **Your Chrome** (with the extension) — your real logged-in sessions. The
  agent only touches it when you explicitly ask.
- **Obscura** (separate stealth browser) — the agent's default browser, so
  automation never disturbs your tabs. Cookie-synced from Chrome daily.

## Security

- Everything listens on `127.0.0.1` only. No inbound network exposure.
- No credentials, tokens, or keys are stored in this repo. The installer asks
  for nothing except, optionally, your ngrok authtoken for remote access.
- The extension requests `debugger` + host permissions because that is
  literally its job (driving tabs); the source is right here in
  `extension/background.js` — read it before loading.

## License

Apache 2.0 — see `LICENSE` and `NOTICE`. Obscura is a separate upstream
project ([h4ckf0r0day/obscura](https://github.com/h4ckf0r0day/obscura),
Apache 2.0) and is not included here.
