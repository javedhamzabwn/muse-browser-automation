"""core/adapters/http_adapter.py — Tier 0 Fast Static Fetcher (<20ms latency)."""

from __future__ import annotations

import logging
import time
import urllib.request
from typing import Any, Dict, Optional

from core.adapters.base import BaseToolAdapter
from core.fetch.extractor import SimpleContentExtractor
from core.fetch.normalizer import FetchResult

logger = logging.getLogger("muse.adapters.http")


class HttpStaticAdapter(BaseToolAdapter):
    """Ultra-fast, zero-overhead static HTTP fetcher."""

    name = "http_static"

    async def fetch(self, url: str, options: Optional[Dict[str, Any]] = None) -> FetchResult:
        opts = options or {}
        timeout = float(opts.get("timeout", 10.0))
        headers = {
            "User-Agent": opts.get("user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        t0 = time.perf_counter()
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                status_code = resp.status
                encoding = resp.headers.get_content_charset() or "utf-8"
                html = raw.decode(encoding, errors="replace")

            t_fetch = (time.perf_counter() - t0) * 1000.0

            # Extract structured text and links
            extracted = SimpleContentExtractor.extract(html, base_url=url)
            t_total = (time.perf_counter() - t0) * 1000.0

            return FetchResult(
                success=True,
                tool=self.name,
                url=url,
                title=extracted["title"],
                content=extracted["text"],
                text=extracted["text"],
                html=html if opts.get("return_html") else None,
                links=extracted["links"],
                images=extracted["images"],
                timing={"total_ms": round(t_total, 2), "fetch_ms": round(t_fetch, 2)},
                status_code=status_code,
            )
        except Exception as exc:
            t_total = (time.perf_counter() - t0) * 1000.0
            return FetchResult(
                success=False,
                tool=self.name,
                url=url,
                error=str(exc),
                timing={"total_ms": round(t_total, 2)},
            )
