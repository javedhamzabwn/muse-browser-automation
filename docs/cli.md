# Command Line Interface (CLI) Reference

## Overview

The Muse 4.0 CLI (`cli.py`) provides an interactive terminal menu when invoked without arguments and direct subcommands for scriptable automation and system management.

---

## Interactive Menu Mode

Run:
```bash
python cli.py
```

Presents a 10-option interactive menu:

```text
============================================================
           Muse Browser Automation 4.0 CLI
   Single-Port Multiplexed Platform (127.0.0.1:18010)
============================================================
  1. System & Tool Status
  2. Capability Matrix & Registered Tools
  3. System Doctor & Diagnostic Checks
  4. Tool Installer & Provisioning
  5. Fetch Webpage (Multi-Tier Engine)
  6. Managed Browser Task Execution
  7. Remote & ngrok Tunnel Management
  8. Browser Profile & Session Manager
  9. Run Performance Benchmarks
 10. Start Local Single-Port Daemon
  0. Exit
============================================================
```

---

## Direct Subcommands

### 1. Status & Diagnostics

```bash
# Display overall system status, browser readiness, and cache stats
python cli.py status

# Run full system diagnostics and live component probes
python cli.py doctor

# Display tool registry capability matrix
python cli.py tools --capabilities
```

### 2. Tool Management

```bash
# List all registered tools
python cli.py tools

# Install or download a specific tool
python cli.py install <tool_name>

# Install all missing tools
python cli.py install all
```

### 3. Fetching & Content Extraction

```bash
# Fetch a URL using the optimal fallback tier
python cli.py fetch https://example.com

# Fetch with specific requirements
python cli.py fetch https://example.com --js --cookies

# Force a specific tool
python cli.py fetch https://example.com --tool playwright
```

### 4. Remote & Single-Port Access

```bash
# Check single-port daemon and ngrok tunnel status
python cli.py remote status

# Display tunnel setup instructions
python cli.py remote tunnel
```

### 5. Performance Benchmarks

```bash
# Run latency benchmarks on daemon endpoints and selector resolution
python cli.py benchmark
```

### 6. Daemon Control

```bash
# Start the single-port multiplexed daemon
python daemon/simpled.py
```
