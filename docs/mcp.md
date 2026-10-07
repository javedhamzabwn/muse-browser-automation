# Model Context Protocol (MCP) Server Specification

## Overview

Muse 4.0 implements a fully compliant **Model Context Protocol (MCP)** server multiplexed over HTTP at:

```
http://127.0.0.1:18010/mcp
```

Or remotely via ngrok:

```
https://<ngrok-domain>/mcp
```

All interactions adhere to JSON-RPC 2.0. Both high-level agent tools and low-level browser primitives are supported.

---

## High-Level Agent Tools

These tools allow LLM agents to execute complex browser actions in single declarative tool calls.

### 1. `fetch_url`
Fetches a webpage using the optimal tool based on requirements, with automatic tiered fallback.
- **Parameters**:
  - `url` (string, required): The target web URL.
  - `force_tool` (string, optional): Specific tool to use (`http_static`, `playwright`, `obscura`, etc.).
  - `requirements` (object, optional): Tool requirements (`javascript`, `cookies`, `stealth`, etc.).
  - `cache` (boolean, optional, default: true): Whether to use cache.
- **Returns**: Formatted text with title, status, tool used, duration, and body content.

### 2. `fetch_extract`
Fetches a webpage and extracts clean markdown, structured text, and outgoing links.
- **Parameters**:
  - `url` (string, required): The URL to extract.
  - `extract_links` (boolean, optional, default: true): Extract hyperlinks.
  - `max_length` (integer, optional, default: 50000): Maximum text characters.
- **Returns**: Structured markdown representation of the page content.

### 3. `browser_task`
Creates and dispatches a multi-step managed browser task.
- **Parameters**:
  - `goal` (string, required): High-level description of what to achieve.
  - `url` (string, optional): Starting URL.
  - `steps` (array of objects, optional): Specific sequential action steps.
  - `profile` (string, optional, default: "default"): Profile name.
  - `max_steps` (integer, optional, default: 30): Safety step limit.
- **Returns**: Task ID and initial execution status.

### 4. `browser_open`
Opens a URL in a browser tab and returns high-level page information.
- **Parameters**:
  - `url` (string, required): The URL to navigate to.
  - `wait_until` (string, optional, default: "load"): Wait condition (`load`, `domcontentloaded`, `networkidle`).
- **Returns**: Page title, status code, and tab identifier.

### 5. `browser_extract`
Extracts structured content, text, markdown, or specific CSS selectors from the active browser tab.
- **Parameters**:
  - `selector` (string, optional): CSS selector to extract.
  - `format` (string, optional, default: "markdown"): Output format (`text`, `markdown`, `html`).
- **Returns**: Extracted DOM content.

### 6. `tool_status`
Returns registration and operational status of all browser and fetcher tools in the registry.
- **Parameters**: None.
- **Returns**: JSON list of all tools, installation status, and version strings.

### 7. `tool_health`
Runs active diagnostic probes on all tools and returns real-time health results.
- **Parameters**:
  - `tool_name` (string, optional): Specific tool to probe.
- **Returns**: Detailed health status per tool with error messages if failing.

### 8. `browser_task_status`
Checks progress and results of a managed browser task.
- **Parameters**:
  - `task_id` (string, required): The managed task identifier.
- **Returns**: Current state (`running`, `completed`, `failed`), step index, and checkpoints.

### 9. `browser_task_cancel`
Cancels an ongoing managed browser task.
- **Parameters**:
  - `task_id` (string, required): The task to abort.
- **Returns**: Cancellation confirmation.

---

## Low-Level Browser Primitives

- `navigate(url, timeout_ms)`: Direct page navigation.
- `click(selector, index, timeout_ms)`: Element click with 5-layer selector resolution.
- `type(selector, text, clear, timeout_ms)`: Text input with real keyboard events.
- `screenshot(full_page)`: Base64-encoded visual screenshot capture.
- `tabs_list()`: Enumeration of all open browser tabs and targets.
- `tab_switch(tab_id)`: Switch focus to specific tab.
- `tab_create(url)`: Open a new browser tab.
- `browser_model()`: Compact PageModel extraction (< 50ms) for LLM context.
- `browser_detect_captcha()`: Detects presence of Cloudflare Turnstile, reCAPTCHA, or hCaptcha.

---

## MCP Manager CLI

The runtime tool state is managed dynamically via `python cli.py mcp`:

```bash
# Display live MCP status, endpoints, protocol health, and latency
python cli.py mcp status

# Machine-readable JSON output
python cli.py mcp status --json

# Dynamically enumerate all registered tools from live /mcp gateway
python cli.py mcp tools

# Execute live JSON-RPC initialize and tools/list protocol test
python cli.py mcp test

# Generate configuration for Claude Desktop
python cli.py mcp config --client claude

# Generate configuration for Cursor IDE
python cli.py mcp config --client cursor

# Copy configuration directly to system clipboard
python cli.py mcp copy --client claude

# Display shareable card for remote agents
python cli.py mcp share
```

---

## Connecting External Agent Clients

### 1. Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "muse": {
      "url": "http://127.0.0.1:18010/mcp"
    }
  }
}
```

### 2. Cursor IDE (`.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "muse": {
      "url": "http://127.0.0.1:18010/mcp",
      "type": "http"
    }
  }
}
```

### 3. Remote Claude / Cursor Connection

When Muse is exposed publicly via `python cli.py expose ngrok`, configure client with the dynamic tunnel URL:

```json
{
  "mcpServers": {
    "muse": {
      "url": "https://<your-ngrok-domain>.ngrok-free.app/mcp"
    }
  }
}
```
*Note: Public endpoints automatically enforce the Public Security Policy (`LOCAL ACCESS != PUBLIC ACCESS`).*

