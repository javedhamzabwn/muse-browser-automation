# Obscura sidecar

## What Obscura is

Obscura is a from-scratch browser engine written in Rust — it is **not
Chromium** (embedded V8, its own layout and paint code). Upstream project:
[github.com/h4ckf0r0day/obscura](https://github.com/h4ckf0r0day/obscura),
Apache 2.0.

**Download the `-stealth` build from the upstream releases page yourself.**
The binary is not vendored in this repo (keep this repo light and let the
upstream project's license/attribution travel with its own download).

## Why two browsers

- **Personal Chrome** (driven by the `Muse Browser Control` extension in
  `../extension/`): used when the agent must act inside the user's own
  logged-in sessions, or when the user explicitly wants something saved in
  their browser.
- **Obscura** (this folder): the **default agent browser**. Automation runs
  here so it never steals focus from, or disturbs, the user's personal tabs.

## obscura_helper.py

Drives a running Obscura instance over Chrome DevTools Protocol (default
port **9222**): navigate, snapshot, click, fill, evaluate, screenshot.

**Gotcha:** Obscura's `Runtime.evaluate` rejects anonymous
`function(){...}` wrappers — always wrap JS as **arrow-function IIFEs**
(`(() => { ... })()`).

## profiles.py

Profile manager with subcommands:

| Command   | What it does                                              |
|-----------|-----------------------------------------------------------|
| `main`    | persistent work profile (port 9222)                       |
| `temp`    | throwaway profile cloning current cookies, auto-deletes   |
| `empty`   | blank throwaway profile, auto-deletes                     |
| `sync`    | sync Chrome cookies into the main profile                 |
| `list`    | show running Obscura instances                            |
| `cleanup` | delete stopped temp/empty profiles                        |

## Cookie sync

`tools/export_cookies.py` writes `cookies-export.txt` (Netscape format) into
Downloads daily at 04:00. To give Obscura the user's sessions:

1. Merge `cookies-export.txt` into `<profile>/cookies.json` **on disk**.
2. Restart Obscura.

Note: setting cookies via CDP `Network.setCookies` works for the live
session but does **not** persist in Obscura — the on-disk merge + restart is
required for them to stick.
