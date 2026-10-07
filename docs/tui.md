# Muse Interactive Textual TUI

## Overview

The **Muse Textual TUI** (`core/tui/`) provides a full-terminal interactive cockpit for monitoring, operating, testing, and managing the Muse Browser Automation platform.

### Core Architecture & Single-Port Rule

- The TUI is strictly a **frontend presentation layer**.
- It communicates directly with existing core subsystems:
  - `ExposureManager`
  - `McpManager`
  - `ToolRegistry`
  - `SessionVault`
  - `ValidationRunner`
- **Zero Additional Ports**: All communication continues to flow through the single multiplexed gateway at `127.0.0.1:18010`. The TUI does **not** create or require any additional ports or background servers.
- **Source of Truth**: Tool lists, MCP schemas, and active URLs are queried dynamically from the runtime gateway; nothing is hardcoded.

---

## Launching the TUI

```bash
# Launch via subcommand
python cli.py tui

# Or via flag
python cli.py --tui

# Or select Option 8 from the interactive CLI menu
python cli.py
```

### Dependency Handling

If `textual` is not installed, the CLI gracefully alerts the user:

```text
Textual is not installed.

Install with:

pip install textual
```

---

## Keyboard Controls & Navigation

| Key | Action | Description |
| :--- | :--- | :--- |
| `1` | Switch to **Dashboard** | Overview of Gateway, MCP, Exposure, and Subsystems |
| `2` | Switch to **Tools** | Interactive tool browser, search, filters, and schema inspector |
| `3` | Switch to **MCP** | MCP protocol diagnostics, latency, copy config, and share |
| `4` | Switch to **Exposure** | Switch modes (LOCAL, NGROK, BOTH, OFF) with safety prompts |
| `5` | Switch to **Sessions** | Session Vault metadata, online validation, and revocation |
| `6` | Switch to **Terminal** | Interactive local shell (PowerShell / cmd) |
| `7` | Switch to **Validation** | Real-world 6-category validation matrix |
| `8` | Switch to **Tests** | Automated unit & integration test runner |
| `9` | Switch to **Settings** | Refresh interval, preferred backend, and public exceptions |
| `Ctrl + R` | **Refresh** | Immediate poll of live telemetry |
| `Ctrl + Q` | **Quit** | Cleanly exits the TUI without terminating background daemons |

---

## Mouse Support

Full mouse support is active across the interface:
- **Sidebar**: Click any navigation item to switch screens.
- **Buttons**: Click toolbars, modal buttons, and actions.
- **Tables**: Click row headers or rows to select items. Double click or press Enter on tools to view detailed schemas.
- **Modals**: Click background or buttons to dismiss.
- **Scroll**: Mouse wheel scrolls logs, schemas, and tables.

---

## Screens Reference

### 1. Dashboard
Displays live gateway state, port 18010, local MCP URL, dashboard URL, active exposure mode, and health status for Browser runtimes, Computer Control, Terminal, and Session Vault.

### 2. Tools
Scrollable `DataTable` displaying all dynamic MCP tools. Features search filtering by name/description and category dropdowns (Browser, Fetcher, Computer, Session, Terminal, System). Clicking "Inspect Tool Details" opens a modal showing description, backend, public exposure policy, and JSON-RPC input schema.

### 3. MCP
Deep protocol inspector. Tests local and public endpoints via live `initialize` and `tools/list` JSON-RPC requests, measures round-trip latency, and offers one-click clipboard copying for Claude Desktop (`claude_desktop_config.json`) and Cursor IDE (`mcp.json`).

### 4. Exposure
Controls single-port gateway exposure. Setting `NGROK` or `BOTH` triggers an administrative confirmation modal detailing that sensitive capabilities (computer control, session vault, terminal) remain protected and denied to public tunnel requests.

### 5. Sessions
Integrates the `SessionVault`. Lists session ID, domain, browser, profile, and status. Enforces a **Zero Raw Secrets Policy** — cookies and auth tokens are never displayed. Allows online session validation and revocation.

### 6. Terminal
Interactive local shell terminal (PowerShell on Windows, Bash on Unix). Executes commands in background workers with real-time output streaming.
- **Security Policy**: Terminal execution is **LOCAL ONLY**. Remote execution over public ngrok tunnels is **DENIED** by default.

### 7. Validation
Executes the comprehensive 6-category real-world test matrix:
1. Synthetic Tests
2. Local Tool Tests
3. Real Website Tests
4. Browser Session Tests
5. Computer Use Tests
6. MCP Integration Tests
Never converts failures or degraded states into false passes.

### 8. Tests
Runs automated test suites inside background threads. Allows running fast core diagnostics or spawning the full `tests/run_tests.py` suite without freezing the terminal interface.

### 9. Settings
Configures telemetry poll frequency (2s, 3s, 5s, 10s), preferred browser automation backend, and public security exceptions.

---

## Troubleshooting

- **Textual missing**: Run `pip install textual`.
- **TUI displays Gateway OFFLINE**: Navigate to **Dashboard** and click **Start / Ensure Gateway**, or run `python cli.py start` in a separate terminal.
- **ngrok NOT EXPOSED**: Navigate to **Exposure**, select **Expose via ngrok**, and confirm the public exposure warning dialog.
