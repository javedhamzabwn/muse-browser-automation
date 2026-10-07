# Muse Browser Automation 4.0 — Architecture

## Overview

Muse Browser Automation 4.0 is a unified, blazing-fast, self-healing browser automation and web fetching platform for AI agents. It operates under a strict **Single-Port Principle**, multiplexing MCP, REST APIs, WebSockets, Server-Sent Events, dashboards, and remote tunnels through one local port (`127.0.0.1:18010`).

```
                +-----------------------------------------+
                |        AI Agent / MCP Client            |
                +--------------------+--------------------+
                                     |
                    HTTP / JSON-RPC / WebSocket
                                     v
+-------------------------------------------------------------------------+
|                  MUSE SINGLE-PORT RUNTIME (127.0.0.1:18010)             |
|                                                                         |
|  /mcp                 /api/browser/...       /ws           /dashboard   |
|  (JSON-RPC 2.0)       (REST Endpoints)       (Multiplex)   (Web UI)     |
|                                                                         |
|  /health              /status                /events       /tool        |
|  (Probes)             (Telemetry)            (SSE Stream)  (Legacy)     |
+------------------------------------+------------------------------------+
                                     |
             +-----------------------+-----------------------+
             v                                               v
+-------------------------+                     +-------------------------+
|   UNIVERSAL FETCH ENGINE|                     |   BROWSER RUNTIME POOL  |
|                         |                     |                         |
|  - Requirement Planner  |                     |  - Playwright Chromium  |
|  - 5-Tier Fallback      |                     |  - Google Chrome (CDP)  |
|  - Circuit Breakers     |                     |  - Obscura Stealth      |
|  - Failure Memory       |                     |  - Agent-Browser CLI    |
|  - SQLite L1/L2 Cache   |                     |  - Moli / Lightpanda    |
+------------+------------+                     +------------+------------+
             |                                               |
             +-----------------------+-----------------------+
                                     v
                      +-----------------------------+
                      |    TARGET WEBSITES & APIS   |
                      +-----------------------------+
```

---

## Core Components

### 1. Single-Port Multiplexed Daemon (`daemon/simpled.py`)
- Listens on `127.0.0.1:18010`.
- Routes all incoming traffic according to URL path:
  - `/mcp` — Model Context Protocol JSON-RPC 2.0 endpoint (tools, resources, prompts).
  - `/api/browser/...` — RESTful browser lifecycle and inspection APIs.
  - `/ws` — Bidirectional WebSocket for real-time streaming, element highlighting, and actions.
  - `/events` — SSE stream for task progress, DOM mutations, and agent status.
  - `/dashboard`, `/` — Embedded HTML/CSS control center with live telemetry.
  - `/health`, `/status` — JSON health checks and runtime diagnostics.
  - `/tool` — Backward-compatible action dispatch.

### 2. Central Tool Registry (`core/tools/`)
- Dynamic capability matching instead of hardcoded tool names.
- Manifest definitions for all supported tools:
  - Categories: `browser`, `fetcher`, `parser`, `utility`.
  - Capabilities: `javascript`, `cookies`, `login`, `screenshot`, `fast_fetch`, `stealth`, `media_download`, `transcoding`.
- Auto-detection across system paths, virtual environments, and custom directories.
- Non-blocking active health checks and version extraction.
- Single and batch tool installer framework.

### 3. Universal Fetch Engine (`core/fetch/`)
- Tiered execution strategy:
  - **Tier 0**: Python `urllib` / `aiohttp` static fetcher (< 50ms).
  - **Tier 1**: Lightweight headless browser / parser (Lightpanda, Redlib failover).
  - **Tier 2**: Full headless JavaScript execution (Playwright, Obscura).
  - **Tier 3**: Authenticated real user browser (Chrome profile, Camoufox).
  - **Tier 4**: Human assistance request for irreversible CAPTCHA / 2FA.
- Persistent SQLite cache with SHA-256 keying and TTL management.
- Normalized output schema (`FetchResult`) returning clean text, markdown, HTML, metadata, and extracted links.

### 4. Self-Healing Fallback & Resilience (`core/fetch/fallback.py`)
- Error classifier categorizing HTTP and browser errors into 10 deterministic types.
- Per-tool circuit breakers with configurable failure thresholds and cooldown periods.
- Failure memory tracking domain-specific tool incompatibilities to prevent repeated failure loops.

### 5. Session & Profile Management (`core/sessions/manager.py`)
- Isolated browser profiles per task or user persona.
- Automatic storage state isolation (cookies, localStorage, indexedDB).
- Safe cookie export with strict terminal and log masking (never prints raw session tokens).
- Explicit deletion confirmation safeguards.

### 6. Remote Tunneling & ngrok Detection
- Automatically detects active ngrok tunnels via local inspection API (`127.0.0.1:4040`).
- Dynamically advertises public remote endpoints (`https://<ngrok-domain>/mcp`).
- Requires zero extra public ports; ngrok tunnels directly to `18010`.
