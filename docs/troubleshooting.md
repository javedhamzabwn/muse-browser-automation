# Troubleshooting & Diagnostic Guide

## Overview

Common operational scenarios, error resolutions, and diagnostic procedures for Muse 4.0.

---

## Diagnostic Procedures

### Run System Doctor
First step in diagnosing any tool or environment issue:
```bash
python cli.py doctor
```
Checks:
- Python 3.10+ runtime and packages.
- Node.js runtime for agent-browser and Playwright driver.
- Chrome executable path and permissions.
- Daemon reachability on port 18010.
- Live tool execution readiness.

---

## Common Issues & Solutions

### 1. Port 18010 Already in Use (`[WinError 10048]`)
- **Cause**: A previous daemon process or orphaned background worker is still running.
- **Solution**:
  - Identify the process on Windows PowerShell:
    ```powershell
    Get-NetTCPConnection -LocalPort 18010 | Select-Object OwningProcess
    ```
  - Stop the process:
    ```powershell
    Stop-Process -Id <PID> -Force
    ```
  - Restart daemon: `python daemon/simpled.py`.

### 2. Obscura Not Detected
- **Cause**: Binary is missing from `~/.muse/bin/` and local path.
- **Solution**:
  - Place `obscura.exe` in `~/.muse/bin/` or `~/obscura/obscura.exe`.
  - Or run:
    ```bash
    python cli.py install obscura
    ```

### 3. Playwright Chromium Driver Missing
- **Cause**: Playwright package installed but browser binaries not downloaded.
- **Solution**:
  ```bash
  python -m playwright install chromium
  ```

### 4. ngrok Tunnel Not Detected
- **Cause**: ngrok agent is not running or web inspection port (4040) is blocked.
- **Solution**:
  - Start ngrok pointing to the single port:
    ```bash
    ngrok http 18010
    ```
  - Verify local web inspector at `http://127.0.0.1:4040`.

### 5. High-Risk Action Blocked
- **Cause**: Task requested an action with high risk (e.g. form submission on sensitive domain).
- **Solution**: Task is in `WAITING_APPROVAL`. Call `/api/browser/task/<id>/approve` or confirm via MCP.
