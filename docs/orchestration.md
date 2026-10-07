# Universal Fetch Engine & Tool Orchestration

## Overview

The Universal Fetch Engine (`core/fetch/engine.py`) coordinates fetching and content extraction across heterogeneous web tools. It abstracts away underlying browser and HTTP complexities, choosing the lightest, fastest tool that satisfies task requirements.

---

## Architecture

```
                    Incoming URL Request
                             |
                             v
                  [1. Check SQLite Cache] -----> Cache Hit (< 1ms)
                             | (Cache Miss)
                             v
                [2. Requirement Analysis]
                - Needs JavaScript?
                - Needs Cookies / Auth?
                - Needs Anti-Bot Stealth?
                - Reddit URL? (Redlib optimization)
                             |
                             v
                [3. Execution Planner]
                Generates Tiered Candidate Plan
                             |
                             v
               +---> [4. Execute Candidate Tool]
               |             |
               |     +-------+-------+
               |     | Success?      |
               |     v               v
               |   [YES]            [NO]
               |     |               |
               |  Extract &       [5. Error Classification & Circuit Breakers]
               |  Normalize          |
               |     |            Record Failure Memory
               |  Save to Cache      |
               |     |            Select Next Fallback Tier
               |     v               |
               |  Return Result      +---------------+
```

---

## 5-Tier Fallback Hierarchy

1. **Tier 0 — Fast HTTP Static Fetcher**:
   - `http_static` (urllib / aiohttp).
   - Latency: < 50ms. Zero browser overhead. Used for standard HTML, APIs, documentation.
2. **Tier 1 — Lightweight Headless / Parser**:
   - `lightpanda`, `redlib` (for Reddit).
   - Fast, stripped-down JS or alternative frontend mirrors.
3. **Tier 2 — Full Headless JS Automation**:
   - `playwright`, `obscura`.
   - Full DOM hydration, SPA navigation, and screenshot capabilities.
4. **Tier 3 — Authenticated Real Browser**:
   - `chrome` with user profile, `camoufox`.
   - Full human browser environment for protected login sessions and anti-bot bypass.
5. **Tier 4 — Human-in-the-Loop**:
   - Pauses task in `WAITING_HUMAN` state.
   - For physical hardware 2FA keys, interactive SMS codes, or complex perceptual puzzles.

---

## Normalized Output Schema (`FetchResult`)

All tools emit an identical, structured data model (`core/fetch/normalizer.py`):

```python
@dataclass
class FetchResult:
    url: str
    status_code: int
    title: str
    content: str            # Clean text/markdown
    raw_html: str           # Raw unmodified HTML
    content_type: str       # MIME type
    tool_used: str          # Tool name that produced result
    tier_used: int          # Tier level (0 - 4)
    duration_ms: float      # Elapsed execution time
    success: bool           # Operation outcome
    links: list[dict]       # Extracted hyperlinks
    metadata: dict          # Headers, cookies, extra attributes
```
