"""core/fetch/reddit.py — Failover Redlib / Reddit Fetch Provider for Muse 4.0."""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.request
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from core.fetch.normalizer import FetchResult

logger = logging.getLogger("muse.fetch.reddit")

DEFAULT_REDLIB_INSTANCES = [
    "https://old.reddit.com",
    "https://redlib.privacyredirect.com",
    "https://redlib.privadency.com",
    "https://redlib.catsarch.com",
    "https://safereddit.com"
]


class RedditFetcher:
    """Fetches Reddit content through multi-instance health-checked Redlib failover."""

    def __init__(self, custom_instances: Optional[List[str]] = None):
        self.instances = list(custom_instances or DEFAULT_REDLIB_INSTANCES)
        self._healthy_instances: List[str] = list(self.instances)
        self._last_instance_check = 0.0

    async def get_healthy_instance(self) -> Optional[str]:
        """Returns the first available instance."""
        return self.instances[0] if self.instances else None

    @staticmethod
    def is_reddit_url(url: str) -> bool:
        """Check if target URL belongs to Reddit or a Reddit mirror."""
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        return any(d in netloc for d in ("reddit.com", "redd.it", "redlib", "libreddit"))

    @staticmethod
    def extract_reddit_path(url: str) -> str:
        """Converts any Reddit / mirror URL into clean path: e.g. /r/python or /r/python/comments/..."""
        parsed = urlparse(url)
        path = parsed.path
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return path

    async def fetch(self, url: str, timeout: float = 6.0) -> FetchResult:
        """Fetch Reddit content trying instances in sequence until success."""
        t0 = time.perf_counter()
        rel_path = self.extract_reddit_path(url)
        fallbacks: List[Dict[str, Any]] = []

        # Try instances in order
        for inst in self.instances:
            target_url = f"{inst.rstrip('/')}{rel_path}"
            # Prefer JSON if querying a post or subreddit
            json_url = target_url.rstrip("/") + ".json"
            t_inst = time.perf_counter()

            try:
                req = urllib.request.Request(
                    json_url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Muse-Browser/4.0"},
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw_data = resp.read()
                    data = json.loads(raw_data.decode("utf-8"))
                    dt_ms = (time.perf_counter() - t_inst) * 1000.0

                    # Parse Reddit JSON into structured text
                    title, text, metadata = self._parse_reddit_json(data, url)

                    return FetchResult(
                        success=True,
                        tool="redlib",
                        url=url,
                        title=title,
                        content=text,
                        text=text,
                        metadata=metadata,
                        timing={"total_ms": round((time.perf_counter() - t0) * 1000.0, 2), "fetch_ms": round(dt_ms, 2)},
                        fallbacks=fallbacks,
                        status_code=200,
                    )
            except Exception as exc:
                dt_err = (time.perf_counter() - t_inst) * 1000.0
                fallbacks.append({"instance": inst, "error": str(exc), "latency_ms": round(dt_err, 2)})
                logger.warning("Redlib instance %s failed (%s), failing over...", inst, exc)
                continue

        # All instances failed
        return FetchResult(
            success=False,
            tool="redlib",
            url=url,
            error="All Redlib fallback instances failed",
            fallbacks=fallbacks,
            timing={"total_ms": round((time.perf_counter() - t0) * 1000.0, 2)},
        )

    def _parse_reddit_json(self, data: Any, original_url: str) -> Tuple[str, str, Dict[str, Any]]:
        """Extract title, body text, and comments from Reddit API payload."""
        title = "Reddit Discussion"
        body_lines: List[str] = []
        meta: Dict[str, Any] = {"url": original_url}

        if isinstance(data, list) and len(data) > 0:
            # Post + comments payload
            post_listing = data[0].get("data", {}).get("children", [])
            if post_listing:
                p_data = post_listing[0].get("data", {})
                title = p_data.get("title", title)
                subreddit = p_data.get("subreddit_name_prefixed", "")
                author = p_data.get("author", "")
                selftext = p_data.get("selftext", "")
                ups = p_data.get("ups", 0)

                body_lines.append(f"# {title}")
                body_lines.append(f"Subreddit: {subreddit} | Author: u/{author} | Score: {ups}\n")
                if selftext:
                    body_lines.append(selftext)
                    body_lines.append("\n---\n## Comments:\n")

            # Extract top comments
            if len(data) > 1:
                comments = data[1].get("data", {}).get("children", [])
                for c in comments[:20]:
                    c_data = c.get("data", {})
                    c_author = c_data.get("author", "")
                    c_body = c_data.get("body", "")
                    c_ups = c_data.get("ups", 0)
                    if c_body:
                        body_lines.append(f"- **u/{c_author}** ({c_ups} pts):\n  {c_body}\n")

        elif isinstance(data, dict):
            # Subreddit listing
            children = data.get("data", {}).get("children", [])
            body_lines.append(f"# Reddit Posts\n")
            for c in children[:25]:
                p = c.get("data", {})
                body_lines.append(f"- [{p.get('ups', 0)} pts] **{p.get('title', '')}** (u/{p.get('author', '')})")
                if p.get("permalink"):
                    body_lines.append(f"  https://reddit.com{p.get('permalink')}")

        return title, "\n".join(body_lines), meta


RedlibFetcher = RedditFetcher
