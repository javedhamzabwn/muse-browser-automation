"""core/fetch/planner.py — Tiered Fetch Execution Planner for Muse 4.0."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from core.fetch.reddit import RedditFetcher


class FetchTier:
    TIER_0_STATIC = 0      # HTTP / urllib / aiohttp
    TIER_1_LIGHTWEIGHT = 1  # Moli, Lightpanda
    TIER_2_FULL_JS = 2      # Playwright Chromium, Obscura stealth, agent-browser, Camoufox
    TIER_3_REAL_BROWSER = 3 # Real Chrome with profile, CSI
    TIER_4_HUMAN = 4        # Human approval / verification


class FetchPlanner:
    """Analyzes task requirements and constructs prioritized tier execution plan."""

    @classmethod
    def plan(cls, url: str, requirements: Optional[Dict[str, Any]] = None) -> List[str]:
        reqs = requirements or {}
        chain: List[str] = []
        
        # 0. Explicit tool/backend override
        override = reqs.get("backend") or reqs.get("tool")
        if override:
            return [override.lower()]

        # 1. Specialized domains
        if RedditFetcher.is_reddit_url(url):
            chain.append("redlib")
            # Skip http_static for Reddit because it returns empty SPA shells or gets blocked.
            # Fall back directly to real browsers (anti-detect preferred).
            chain.extend(["agent-browser", "camoufox", "playwright", "chrome"])
            return cls._dedup(chain)

        # 2. Authentication or real session required -> Tier 3
        if reqs.get("real_browser") or reqs.get("authentication") or reqs.get("persistent_session"):
            chain.extend(["chrome", "csi", "playwright"])
            return cls._dedup(chain)

        # 3. JavaScript explicitly required -> Tier 1 then Tier 2
        if reqs.get("javascript"):
            chain.extend(["playwright", "obscura", "lightpanda", "moli", "agent-browser", "camoufox"])
            return cls._dedup(chain)

        # 4. Standard public fetch -> Tier 0 first (ultra-fast <20ms), fallback to Tier 1 & 2
        chain.extend(["http_static", "playwright", "obscura", "lightpanda", "moli"])
        return cls._dedup(chain)

    @staticmethod
    def _dedup(items: List[str]) -> List[str]:
        seen = set()
        res = []
        for x in items:
            if x not in seen:
                seen.add(x)
                res.append(x)
        return res
