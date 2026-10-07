# Security & Governance Architecture

## Overview

Muse Browser Automation 4.0 enforces strict security boundaries to protect sensitive credentials, prevent unauthorized access, and guard against runaway automation loops.

---

## Single-Port Security & Network Isolation

- **Localhost Binding**: The daemon binds strictly to `127.0.0.1:18010` by default. It does not listen on `0.0.0.0` unless explicitly configured.
- **Port Multiplexing**: Eliminates firewall clutter and unauthorized ports. Remote access is funneled exclusively through authenticated reverse proxies or secure ngrok tunnels.

---

## Credential & Cookie Protection

- **Masked Token Output**: Cookie values, Authorization headers, and session tokens are automatically sanitized in logs, CLI outputs, and MCP inspection payloads.
- **Storage State Sandboxing**: Playwright and Chrome storage states are written to user-isolated paths under `~/.muse/profiles/` with restricted filesystem permissions.
- **Destructive Deletion Confirmation**: Profile deletion API requires explicit confirmation parameters to prevent accidental purging of session data.

---

## Action Verification & Risk Mitigation

- **High-Risk Action Flagging**: Mutations affecting financial transactions, password changes, or irreversible account actions are flagged.
- **Approval Checkpoints**: Tasks containing high-risk actions transition to `WAITING_APPROVAL` and require explicit agent or human confirmation before DOM execution.
- **Task Budget Governor**:
  - Max runtime constraints (e.g. 300 seconds default).
  - Max action limit (e.g. 50 actions default).
  - Automatic abort if action loop or infinite scroll runaway is detected.
