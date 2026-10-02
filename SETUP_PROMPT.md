# SETUP PROMPT — paste this into Muse along with the repo link

> **Repo:** https://github.com/rehantheorylab-pixel/muse-browser-automation
>
> **Prompt to paste:**
>
> Set up the browser automation stack from this repo on my Windows PC:
> https://github.com/rehantheorylab-pixel/muse-browser-automation
>
> Do everything yourself through the terminal. Work through install/install.ps1,
> then the manual Chrome step, then the Obscura section, then verify end to end.
> Read docs/ARCHITECTURE.md first so you know how the pieces fit.
>
> Rules:
> - You already have terminal access on my PC — use it. Do not ask me to run
>   commands or download files by hand; fetch what you need yourself.
> - The ONLY thing you may ask me for is my ngrok authtoken (only if I want
>   remote access to this PC; otherwise skip it entirely). Nothing else.
> - The one step you cannot do yourself: loading the unpacked extension in
>   Chrome (chrome://extensions → Developer mode → Load unpacked). Give me
>   the exact 4-click instruction for that and wait for my "done".
> - Obscura: download the -stealth build from the upstream releases page
>   (see obscura/README.md). Never substitute another binary.
> - When every check in the verification list passes, say "AUTOMATION READY"
>   and start taking browser tasks.

## What "set it up" means (the agent's checklist)

1. **Read** `docs/ARCHITECTURE.md` — ports, components, data flow.
2. **Install:** clone the repo, run `install/install.ps1` in PowerShell.
   It copies files to `%USERPROFILE%\muse-browser-mcp`, installs the
   `websockets` Python package, registers the daemon for auto-start on
   login, starts it now, and creates the daily 04:00 cookie-export task.
3. **Chrome extension (needs the human, 1 minute):** tell the user exactly:
   open `chrome://extensions` → enable Developer mode → Load unpacked →
   select `%USERPROFILE%\muse-browser-mcp\extension`. Wait for their "done".
4. **Verify the daemon:** `POST http://127.0.0.1:18010/tool`
   with `{"tool": "tabs.list", "args": {}}` must return the open tabs.
5. **Obscura (default agent browser):** download the upstream -stealth build,
   install to `%USERPROFILE%\obscura`, set up the `main` profile on CDP port
   9222 via `obscura/profiles.py`, and sync Chrome cookies into it
   (`profiles.py sync`). See `obscura/README.md`.
6. **Remote access (optional):** ONLY if the user wants it — ask for their
   ngrok authtoken, configure `ngrok http 18010` (or the bridge of their
   choice). This is the single permitted question. Nothing else.
7. **End-to-end proof:** through the daemon, list tabs, navigate one tab to
   example.com, screenshot it, and read the title back. Then say
   **AUTOMATION READY**.

## Notes for the installing agent

- Everything is loopback-only (`127.0.0.1`). Nothing phones home.
- The extension never steals window focus: it drives background tabs via CDP.
- If port 18010 is already in use, don't start a second daemon — check
  `tabs.list` first; a live daemon is a finished step, not an error.
- Never ask for passwords, API keys, or OTP codes. The ngrok authtoken is
  the only secret you may request, and only for the optional remote step.
