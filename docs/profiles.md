# Profile Management & Isolation

## Overview

Muse 4.0 provides isolated browser profiles (`core/sessions/manager.py`) to manage authentication states, cookies, cache, and preferences across independent tasks and workflows.

---

## Profile Architecture

Each profile represents a sandboxed environment:

- **Directory**: `~/.muse/profiles/<profile_name>/`
- **Metadata**: Stored in `profile.json` (created timestamp, last used, user agent, proxy settings).
- **Storage State**:
  - `storage_state.json`: Playwright-compatible cookie and localStorage state.
  - User data directory for Chrome CDP sessions.

```
~/.muse/profiles/
├── default/
│   ├── profile.json
│   └── storage_state.json
├── research_agent/
│   ├── profile.json
│   └── storage_state.json
└── e2e_testing/
    ├── profile.json
    └── storage_state.json
```

---

## Cookie Security & Privacy Masking

A critical security principle in Muse 4.0 is that **sensitive credentials and session tokens must never be exposed** in terminal outputs, debug logs, or MCP inspection results:

1. **Masked Cookie Export**:
   - The `export_cookies(profile_name, mask_values=True)` function replaces sensitive cookie values (e.g. `sessionid`, `auth_token`, `jwt`) with asterisks (e.g. `s3c***`).
   - Terminal commands and logs always display masked cookies.
2. **Raw Token Protection**:
   - Raw cookie values remain strictly within encrypted/protected local disk storage states.
   - MCP endpoints filter cookie headers before returning fetch results.

---

## Safe Profile Deletion

To prevent accidental data loss:
- The default profile (`default`) is immutable and cannot be deleted.
- Deletion of non-default profiles requires explicit confirmation:
  ```python
  profile_mgr.delete_profile(name="temp_profile", confirm=True)
  ```
- Profiles currently active in running browser sessions cannot be deleted until closed.

---

## CLI Profile Commands

```bash
# List all configured profiles
python cli.py profiles list

# Create a new isolated profile
python cli.py profiles create my_profile --user-agent "Mozilla/5.0..."

# Switch active profile
python cli.py profiles switch my_profile

# Export masked cookies for inspection
python cli.py profiles cookies my_profile
```
