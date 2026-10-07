# Browser Engines & Runtime Architecture

## Overview

Muse 4.0 integrates multiple specialized browser engines into a unified lifecycle pool. Different tasks require different browser trade-offs: speed, stealth, JavaScript execution depth, or authenticated user sessions.

---

## Supported Browser Runtimes

### 1. Playwright Chromium Engine (`core/adapters/playwright_adapter.py`)
- **Role**: Primary general-purpose automation and headless testing engine.
- **Characteristics**: Fast startup (~800ms), robust DOM manipulation, full CDP event streaming.
- **Use Cases**: Standard web scraping, automated interactions, screenshot generation, unit verification.

### 2. Obscura Stealth Browser (`core/adapters/obscura_adapter.py`)
- **Role**: High-stealth browser for sites with aggressive anti-bot protection (Cloudflare, Akamai, Datadome).
- **Characteristics**: Binary executable with native fingerprint randomization, TLS fingerprint masking, and automated setup.
- **Auto-Provisioning**: Downloaded automatically or picked up from local paths (e.g. `~/obscura/obscura.exe`).
- **Use Cases**: E-commerce protection, anti-bot bypass, high-value extraction.

### 3. Google Chrome with User Profiles (`core/adapters/chrome_adapter.py`)
- **Role**: Authenticated live browser using existing local Chrome user profiles.
- **Characteristics**: Connects to existing user cookies, extensions, and logged-in states via Chrome DevTools Protocol (CDP).
- **Use Cases**: Operating within active SaaS portals, authenticated social accounts, Google Workspace.

### 4. agent-browser CLI (`core/adapters/cli_browser_adapter.py`)
- **Role**: Command-line browser wrapper designed for AI agent interaction.
- **Characteristics**: Fast single-command page interaction and semantic snapshot extraction.
- **Use Cases**: Agent fallback when full programmatic browser connection is unnecessary.

### 5. Camoufox Engine (Planned/Integrated Adapter)
- **Role**: Stealth Firefox-based browser runtime with fingerprint evasion at the C++ level.
- **Characteristics**: Native browser engine level modifications preventing JavaScript-level detection.

### 6. Lightpanda JS Engine (Planned/Integrated Adapter)
- **Role**: Ultra-lightweight headless JavaScript browser written in Zig/C.
- **Characteristics**: 10x lower memory footprint and instant startup compared to Chromium.

---

## Connection & Pool Management

- **Connection Reuse**: The runtime pool reuses running browser instances when executing sequential tasks within the same profile.
- **Graceful Cleanup**: Automatic timeout and process lifecycle management ensures orphan browser processes are terminated when tasks complete.
- **Headless vs Headed**: Configurable via `BrowserConfig(headless=True/False)`. Stealth adapters default to appropriate user-agent emulation.
