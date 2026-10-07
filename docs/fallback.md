# Error Classification, Fallback & Self-Healing

## Overview

Web automation in adversarial environments frequently encounters network blips, bot detection challenges, dynamic DOM changes, and rate limits. Muse 4.0 integrates an automated **Error Classifier**, **Circuit Breaker**, and **Failure Memory** system (`core/fetch/fallback.py`) to prevent infinite failure loops and enable transparent recovery.

---

## Error Classification (10 Error Classes)

Incoming errors from any tool or network layer are deterministically classified:

| Error Category | Indicators / Status Codes | Recoverable? | Recommended Action |
|---|---|---|---|
| `BOT_DETECTED` | Cloudflare 403/503, "Turnstile", "hCaptcha", "Datadome", "Access Denied" | Yes | Escalate to Obscura stealth or Camoufox |
| `RATE_LIMITED` | HTTP 429, "Too Many Requests", "Retry-After" | Yes | Backoff with jitter, rotate IP or mirror |
| `JS_REQUIRED` | `<noscript>`, blank body with script tags, "JavaScript is disabled" | Yes | Escalate from Tier 0 HTTP to Tier 2 Headless Browser |
| `LOGIN_REQUIRED` | HTTP 401, redirect to `/login`, "Please sign in" | Yes | Escalate to authenticated Chrome profile session |
| `TIMEOUT` | Request timeout, navigation timeout, gateway timeout (504) | Yes | Retry with increased timeout or lighter tool |
| `NETWORK_ERROR` | Connection refused, DNS failure, SSL certificate error | Yes | Retry with exponential backoff |
| `ELEMENT_NOT_FOUND` | Missing DOM selector, dynamic element detachment | Yes | Trigger 5-layer selector resolution fallback |
| `CAPTCHA_CHALLENGE` | Active CAPTCHA iframe requiring human interaction | Partial | Escalate to Obscura solver or Tier 4 human-in-the-loop |
| `MEDIA_PROTECTED` | DRM protection, Widevine, encrypted video stream | No | Abort media extraction; notify agent |
| `FATAL` | Process crash, out-of-memory, unrecoverable system exception | No | Abort task, isolate process, log diagnostics |

---

## Circuit Breakers

To avoid overwhelming broken endpoints or failing tools:
- Each tool maintains a circuit breaker tracking consecutive failures.
- **Trip Condition**: 5 consecutive failures triggers an OPEN circuit.
- **Cooldown**: The tool is bypassed for 60 seconds.
- **Half-Open**: After cooldown, a single canary request tests recovery.

---

## Failure Memory

- Tracks domain-specific tool incompatibilities in memory.
- Example: If `http_static` triggers `JS_REQUIRED` on `twitter.com`, Failure Memory records:
  ```json
  {"domain": "x.com", "incompatible_tool": "http_static", "required_tier": 2}
  ```
- Subsequent requests to `x.com` automatically bypass Tier 0 and immediately launch Tier 2.
