# Muse Browser Automation 4.0

Universal, Blazing-Fast, Self-Healing Browser Infrastructure, Fetch Engine & Tool Orchestrator for AI Agents.

Muse 4.0 evolves web automation from brittle scripts into a deterministic, multi-tier platform capable of handling arbitrary websites (React, Vue, Angular, Next.js, SPAs, Shadow DOM, nested iframes, dynamic IDs, modals, rich text) with **sub-50ms verified actions**, **tiered fallback execution**, **zero arbitrary sleeps**, and **strict single-port architecture**.

---

## Key Highlights

- **Single-Port Architecture (Port 18010)**:
  - Exposes **ONE LOCAL PORT ONLY** (`127.0.0.1:18010`) for all external & AI agent communication.
  - No separate public ports for MCP, REST API, WebSocket, Dashboard, or Health.
  - Unified paths: `/mcp` (MCP JSON-RPC 2.0), `/api/browser/...` (REST), `/ws` (Extension WebSocket), `/dashboard` (Web UI), `/health` (Health), `/events` (SSE), `/status` (Telemetry).
  - Remote tunneling: Single command `ngrok http 18010` or `python cli.py expose ngrok` exposes the entire system including remote MCP (`https://<ngrok-domain>/mcp`).
- **Interactive Textual TUI (`core/tui/`)**:
  - Full-terminal interactive cockpit launched via `python cli.py tui` or `python cli.py --tui`.
  - 9 integrated screens: Dashboard, Tools, MCP, Exposure, Sessions, Terminal, Validation, Tests, Settings.
  - Complete mouse and keyboard navigation (keys 1-9, mouse click, scrollable tables, modal dialogs).
  - Background workers prevent freezing during MCP testing, validation, and automated test runs.
  - Interactive local terminal emulator with real-time process streaming.
- **Exposure Manager & Public Security Policy (`core/exposure/`)**:
  - Central exposure controller supporting 4 modes: `LOCAL`, `NGROK`, `BOTH`, `OFF`.
  - Principle: `LOCAL ACCESS != PUBLIC ACCESS`. Public requests are strictly capability-filtered: browser and fetcher tools are allowed; sensitive host controls (computer-control, session vault, terminal) are restricted by default.
  - Dynamic ngrok port-matching tunnel detection via `127.0.0.1:4040/api/tunnels`.
  - State persisted cleanly in `state/exposure.json` with zero credentials or tokens.
- **Dynamic MCP Gateway & Manager (`core/mcp/`)**:
  - Live tool discovery directly from `/mcp` `tools/list` (runtime source of truth, never hardcoded).
  - Protocol verification testing initialize handshake and tools enumeration over JSON-RPC 2.0.
  - Client configuration generator for Claude Desktop, Cursor IDE, and Generic HTTP/SSE.
  - Direct clipboard export (`python cli.py mcp copy --client claude`).
- **Central Tool Registry & Dynamic Capabilities (`core/tools/`)**:
  - Centralized catalog supporting `playwright`, `chrome`, `obscura`, `moli`, `lightpanda`, `agent-browser`, `camoufox`, `csi`, `redlib`, `yt-dlp`, `zavora`, and `pyautogui`.
  - Dynamic capability matching (`javascript`, `cookies`, `login`, `screenshot`, `fast_fetch`, `stealth`, `media_download`, `transcoding`).
  - Automated system-wide binary detection and active health probes (`python cli.py doctor`).
- **Universal Fetch Engine & 5-Tier Fallback (`core/fetch/`)**:
  - **Tier 0**: Python `urllib` / `aiohttp` static fetcher (<50ms, zero browser overhead).
  - **Tier 1**: Lightweight headless browser / Redlib Reddit failover.
  - **Tier 2**: Full headless JavaScript execution (Playwright Chromium, Obscura).
  - **Tier 3**: Authenticated real user browser (Chrome profile, Camoufox).
  - **Tier 4**: Human-in-the-loop assistance for physical 2FA and complex challenges.
  - Persistent SQLite L1/L2 cache with SHA-256 keying and privacy exclusions.
- **Self-Healing Fallback & Error Classification**:
  - 10-class deterministic error classifier (`BOT_DETECTED`, `RATE_LIMITED`, `JS_REQUIRED`, `LOGIN_REQUIRED`, `TIMEOUT`, `NETWORK_ERROR`, `ELEMENT_NOT_FOUND`, `CAPTCHA_CHALLENGE`, `MEDIA_PROTECTED`, `FATAL`).
  - Per-tool circuit breakers (5 consecutive failure threshold, 60s cooldown).
  - Domain-specific failure memory to avoid repeated failing tiers.
- **Model Context Protocol (MCP) Server (28 Tools)**:
  - High-level agent tools: `fetch_url`, `fetch_extract`, `browser_task`, `browser_open`, `browser_extract`, `tool_status`, `tool_health`, `browser_task_status`, `browser_task_cancel`.
  - Browser primitives: `navigate`, `click`, `type`, `screenshot`, `browser_model`, `tabs_list`, `tab_switch`, `tab_create`, `tab_close`.
- **Durable Task Engine & Profile Management**:
  - Multi-step workflow state machine with SQLite-persisted checkpoints.
  - Profile sandboxing with masked cookie export (never logs or prints raw auth tokens).
  - Safe profile deletion requiring explicit confirmation.
- **10-Option Interactive CLI & Scriptable Subcommands (`cli.py`)**:
  - Full ASCII-safe interactive terminal menu when called without arguments.
  - Subcommands: `status`, `tools`, `doctor`, `install`, `fetch`, `remote`, `navigate`, `model`, `click`, `benchmark`.

---

## Architecture Overview

```
                      +-----------------------------------------+
                      |        AI Agent / MCP Client            |
                      +--------------------+--------------------+
                                           |
                          HTTP / JSON-RPC / WebSocket
                                           v
+-------------------------------------------------------------------------------+
|                    MUSE SINGLE-PORT RUNTIME (127.0.0.1:18010)                 |
|                                                                               |
|  /mcp                 /api/browser/...       /ws                 /dashboard   |
|  (JSON-RPC 2.0)       (REST Endpoints)       (Multiplex)         (Web UI)     |
|                                                                               |
|  /health              /status                /events             /tool        |
|  (Probes)             (Telemetry)            (SSE Stream)        (Legacy)     |
+------------------------------------------+------------------------------------+
                                           |
                   +-----------------------+-----------------------+
                   v                                               v
+-------------------------------+                     +-------------------------+
|     UNIVERSAL FETCH ENGINE    |                     |   BROWSER RUNTIME POOL  |
|                               |                     |                         |
|  - Requirement Planner        |                     |  - Playwright Chromium  |
|  - 5-Tier Fallback            |                     |  - Google Chrome (CDP)  |
|  - Error Classifier           |                     |  - Obscura Stealth      |
|  - Circuit Breakers           |                     |  - Agent-Browser CLI    |
|  - Failure Memory             |                     |  - Moli / Lightpanda    |
|  - Persistent SQLite Cache    |                     |  - Camoufox / CSI       |
+-------------------------------+                     +-------------------------+
```

---

## Quick Start

### 1. Interactive CLI Mode

Launch without arguments to enter the interactive menu:

```bash
python cli.py
```

### 2. Interactive Textual TUI

Launch the full-screen terminal user interface:

```bash
python cli.py tui
# Or
python cli.py --tui
```

### 3. Direct CLI Subcommands

```bash
# Start Muse single-port gateway (interactive mode prompt)
python cli.py start

# Exposure management (local, ngrok, both, off, status)
python cli.py expose status
python cli.py expose status --json
python cli.py expose local
python cli.py expose ngrok
python cli.py expose both
python cli.py expose off

# MCP management (status, tools, test, config, copy, share)
python cli.py mcp status
python cli.py mcp status --json
python cli.py mcp tools
python cli.py mcp test
python cli.py mcp config --client claude
python cli.py mcp copy --client claude
python cli.py mcp share

# System status & tool catalog
python cli.py status

# Capability matrix of all registered tools
python cli.py tools --capabilities

# Run live system diagnostics and health probes
python cli.py doctor

# Fetch any URL using multi-tier fallback
python cli.py fetch https://news.ycombinator.com

# Run performance benchmark suite
python cli.py benchmark

# Stop Muse gateway and exposure tunnels
python cli.py stop
```

### 3. Web Dashboard

Open the single-port web dashboard at: **`http://127.0.0.1:18010/dashboard`**.

### 4. Running the Test Suite

```bash
python tests/run_tests.py
```

All 63+ tests cover unit, live browser integration, shadow DOM piercing, iframe traversal, cache healing, tool registry, session management, and single-port multiplexing.

---

## Documentation

Detailed documentation available in `docs/`:

- [docs/architecture.md](file:///d:/Javed%20Hamza/Documents/ai_projects/muse/muse-browser-automation/docs/architecture.md) — System architecture & single-port multiplexing.
- [docs/tools.md](file:///d:/Javed%20Hamza/Documents/ai_projects/muse/muse-browser-automation/docs/tools.md) — Tool registry, capabilities, and discovery.
- [docs/browsers.md](file:///d:/Javed%20Hamza/Documents/ai_projects/muse/muse-browser-automation/docs/browsers.md) — Browser runtimes, stealth profiles, and pool management.
- [docs/profiles.md](file:///d:/Javed%20Hamza/Documents/ai_projects/muse/muse-browser-automation/docs/profiles.md) — Session profiles, isolation, and cookie masking.
- [docs/sessions.md](file:///d:/Javed%20Hamza/Documents/ai_projects/muse/muse-browser-automation/docs/sessions.md) — Task state machine, checkpointing, and durability.
- [docs/mcp.md](file:///d:/Javed%20Hamza/Documents/ai_projects/muse/muse-browser-automation/docs/mcp.md) — Model Context Protocol tools and schemas.
- [docs/remote.md](file:///d:/Javed%20Hamza/Documents/ai_projects/muse/muse-browser-automation/docs/remote.md) — ngrok remote tunneling on port 18010.
- [docs/orchestration.md](file:///d:/Javed%20Hamza/Documents/ai_projects/muse/muse-browser-automation/docs/orchestration.md) — Universal fetch engine & planner.
- [docs/fallback.md](file:///d:/Javed%20Hamza/Documents/ai_projects/muse/muse-browser-automation/docs/fallback.md) — Error classification & circuit breakers.
- [docs/cli.md](file:///d:/Javed%20Hamza/Documents/ai_projects/muse/muse-browser-automation/docs/cli.md) — Complete CLI command reference.
- [docs/tui.md](file:///d:/Javed%20Hamza/Documents/ai_projects/muse/muse-browser-automation/docs/tui.md) — Interactive Textual TUI interface and controls.
- [docs/exposure.md](file:///d:/Javed%20Hamza/Documents/ai_projects/muse/muse-browser-automation/docs/exposure.md) — Exposure Manager and Public Security Policy.
- [docs/security.md](file:///d:/Javed%20Hamza/Documents/ai_projects/muse/muse-browser-automation/docs/security.md) — Security boundaries & credential protection.
- [docs/troubleshooting.md](file:///d:/Javed%20Hamza/Documents/ai_projects/muse/muse-browser-automation/docs/troubleshooting.md) — Diagnostics and troubleshooting solutions.

---

## License

Apache 2.0. See `LICENSE` and `NOTICE`.
