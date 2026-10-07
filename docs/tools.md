# Central Tool Registry & Catalog

## Overview

Muse Browser Automation 4.0 uses a centralized, capability-driven tool registry (`core/tools/`). Instead of hardcoding execution paths, tasks express requirements (e.g. `javascript=True`, `cookies=True`, `stealth=True`), and the Capability Matcher dynamically selects the optimal available tool.

---

## Tool Catalog

| Tool Name | Display Name | Category | Primary Capabilities | Install Method | Default Binary / Probe |
|---|---|---|---|---|---|
| `http_static` | Tier 0 Fast HTTP Fetcher | `fetcher` | `fast_fetch` | `builtin` | Python standard library |
| `playwright` | Playwright Chromium Engine | `browser` | `javascript`, `cookies`, `screenshot`, `fast_fetch` | `pip` | `python -m playwright` |
| `chrome` | Google Chrome (User Profile) | `browser` | `javascript`, `cookies`, `login`, `screenshot` | `manual` | System Chrome binary |
| `obscura` | Obscura Stealth Engine | `browser` | `javascript`, `cookies`, `login`, `screenshot`, `stealth` | `download` | `obscura.exe` / `~/.muse/bin/` |
| `agent-browser` | agent-browser CLI | `browser` | `javascript`, `cookies`, `screenshot`, `fast_fetch` | `npm` | `npx agent-browser` |
| `moli` | Moli Browser Engine | `browser` | `javascript`, `cookies`, `screenshot`, `fast_fetch` | `git` | Local git / binary |
| `lightpanda` | Lightpanda Fast JS Engine | `browser` | `javascript`, `fast_fetch` | `download` | `lightpanda.exe` |
| `camoufox` | Camoufox Anti-Detect Browser | `browser` | `javascript`, `cookies`, `stealth` | `pip` | `python -m camoufox` |
| `csi` | Cloudflare Solver Engine | `browser` | `javascript`, `cookies`, `login`, `stealth` | `pip` | Python CSI module |
| `redlib` | Redlib Reddit Fetcher | `fetcher` | `fast_fetch` | `builtin` | Public Redlib mirror pool |
| `yt-dlp` | yt-dlp Media Extractor | `utility` | `media_download` | `pip` | `yt-dlp` binary |
| `ffmpeg` | FFmpeg Transcoder | `utility` | `transcoding` | `manual` | `ffmpeg.exe` binary |

---

## Capability Flags

Capabilities defined in `core/tools/capabilities.py`:

- `JAVASCRIPT`: Engine executes client-side ECMAScript and dynamic DOM updates.
- `COOKIES`: Persists and restores HTTP and browser cookie jars across requests.
- `LOGIN`: Supports user authentication sessions and saved credential states.
- `SCREENSHOT`: Renders high-fidelity full-page and element viewport PNG/WebP images.
- `STEALTH`: Employs TLS/JA3 spoofing, canvas noise, and navigator evasion techniques.
- `FAST_FETCH`: Low-latency, lightweight retrieval path (< 500ms).
- `MEDIA_DOWNLOAD`: Streams and downloads video/audio streams and manifests.
- `TRANSCODING`: Converts media formats and extracts audio tracks.

---

## Tool Health & Discovery

The `SystemDoctor` and `ToolHealthChecker` proactively verify tool readiness:

1. **Auto-Detection**: Scans system `PATH`, standard application directories, Python virtualenv binaries, and `~/.muse/bin/`.
2. **Version Extraction**: Executes non-blocking version probes (e.g. `--version`) with strict timeouts.
3. **Execution Probes**: Evaluates lightweight functional tests (e.g. running Chromium in headless mode, checking urllib connectivity).
4. **State Persistence**: Enables or disables tools via configuration file stored in `~/.muse/tools.json`.

---

## CLI Management Commands

```bash
# View all tools and status
python cli.py tools

# View full capability matrix
python cli.py tools --capabilities

# Run live system health diagnostics
python cli.py doctor

# Install or provision a specific tool
python cli.py install <tool_name>

# Install all missing tools
python cli.py install all
```
