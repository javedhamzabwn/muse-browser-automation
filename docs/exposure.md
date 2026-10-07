# Muse Exposure Manager

## Overview

The **Exposure Manager** (`core/exposure/manager.py`) is the centralized controller responsible for governing all network exposure of the Muse 4.0 runtime.

Adhering strictly to Muse's **Single-Port Architecture**, the Exposure Manager routes all external communication through **Port 18010** (`127.0.0.1:18010`). No separate ports are ever opened for individual tools, computer control, terminal, or MCP.

---

## Exposure Modes

| Mode | Local Gateway (:18010) | ngrok Public Tunnel | Security Scope |
| :--- | :--- | :--- | :--- |
| **`LOCAL`** | `http://127.0.0.1:18010` | Disabled | Full access to all registered tools & computer use |
| **`NGROK`** | `http://127.0.0.1:18010` | Active (`https://<domain>.ngrok-free.app`) | Capability-filtered on public tunnel endpoints |
| **`BOTH`** | `http://127.0.0.1:18010` | Active (`https://<domain>.ngrok-free.app`) | Local callers get full access; public callers filtered |
| **`OFF`** | Offline | Closed | All gateway sockets & managed tunnels stopped |

---

## Public Security Policy (`LOCAL ACCESS != PUBLIC ACCESS`)

Public exposure is not equivalent to local loopback access. To prevent unauthorized remote code execution or sensitive data exfiltration:

1. **Allowed Capabilities on Public Endpoints**:
   - `browser`: Browser automation, navigation, element interaction, tab management.
   - `fetcher`: Static and rendered multi-tier web page extraction.
   - `system_inspect`: Health checks, tool status, version detection.
   - `media`: Media inspection and downloading.

2. **Denied Capabilities on Public Endpoints (Protected by Default)**:
   - `computer_control`: Desktop cursor control, keyboard typing, window enumeration.
   - `session_vault`: Decryption and export of user browser cookies / session credentials.
   - `terminal`: Host command execution.
   - `filesystem`: Arbitrary local file reading or writing.

Overrides can be configured via environment variables (`MUSE_ALLOW_PUBLIC_COMPUTER=1`, `MUSE_ALLOW_PUBLIC_SESSION=1`) or via `state/public_permissions.json`.

---

## CLI Usage

```bash
# Check exposure status
python cli.py expose status

# Output machine-readable JSON status
python cli.py expose status --json

# Set mode to Local only
python cli.py expose local

# Enable ngrok public exposure (prompts security confirmation)
python cli.py expose ngrok

# Enable both Local and ngrok
python cli.py expose both

# Cleanly stop exposure and tunnels
python cli.py expose off
```

---

## State Persistence

Runtime state is recorded in `state/exposure.json`:
- `mode`: Active mode (`local`, `ngrok`, `both`, `off`)
- `local_port`: Port number (default: 18010)
- `local_url`: `http://127.0.0.1:18010`
- `public_url`: Dynamic ngrok URL (or `null`)
- `started_at`: UTC timestamp

Zero secrets, auth tokens, passwords, or cookies are ever written to `exposure.json`.
