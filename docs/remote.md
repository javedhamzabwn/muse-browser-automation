# Remote Tunneling & Single-Port Access

## Overview

Muse Browser Automation 4.0 strictly adheres to the **Single-Port Architecture**. All external interactions — MCP commands, REST API, WebSocket streams, and dashboard UI — are served on a single port (`18010`).

When exposing Muse to remote AI agents (e.g. Anthropic Claude, OpenAI, custom cloud agents), only **one tunnel** is needed.

---

## One-Port Principle

There are **no separate public ports** for:
- MCP (`/mcp`)
- Browser REST API (`/api/...`)
- WebSocket (`/ws`)
- Dashboard (`/dashboard`)
- Health / Status (`/health`, `/status`)
- Events (`/events`)

All services are route-multiplexed behind `http://127.0.0.1:18010`.

---

## Exposing Muse via ngrok

To expose your local Muse instance securely to the internet:

```bash
ngrok http 18010
```

Once running, ngrok assigns a public HTTPS URL (e.g. `https://your-domain.ngrok-free.dev`).

All remote paths automatically map 1:1:

| Service | Local URL | Remote Tunnel URL |
|---|---|---|
| MCP Server | `http://127.0.0.1:18010/mcp` | `https://your-domain.ngrok-free.dev/mcp` |
| Web Dashboard | `http://127.0.0.1:18010/dashboard` | `https://your-domain.ngrok-free.dev/dashboard` |
| WebSocket Stream | `ws://127.0.0.1:18010/ws` | `wss://your-domain.ngrok-free.dev/ws` |
| Health Endpoint | `http://127.0.0.1:18010/health` | `https://your-domain.ngrok-free.dev/health` |
| Browser API | `http://127.0.0.1:18010/api/browser/...` | `https://your-domain.ngrok-free.dev/api/browser/...` |

---

## Automatic ngrok Detection

Muse automatically queries the local ngrok client API (`http://127.0.0.1:4040/api/tunnels`) on startup and during health checks.

- If ngrok is running, Muse auto-populates `remote_mcp_url` in health and status endpoints:
  ```json
  {
    "ok": true,
    "single_port": 18010,
    "ngrok": {
      "connected": true,
      "public_url": "https://your-domain.ngrok-free.dev",
      "remote_mcp_url": "https://your-domain.ngrok-free.dev/mcp"
    }
  }
  ```

---

## CLI Remote Commands

```bash
# Check remote tunnel status and endpoints
python cli.py remote status

# Generate tunnel helper instructions
python cli.py remote tunnel
```
