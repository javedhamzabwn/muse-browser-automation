"""core/validation/browser_validator.py — Real-World Website Matrix Validator."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("muse.validation.browser")


@dataclass
class WebsiteTestResult:
    category: str
    url: str
    backend: str
    success: bool
    status_code: int
    duration_ms: float
    capabilities_verified: Dict[str, str] = field(default_factory=dict)
    blocked_by_site: bool = False
    error: Optional[str] = None


class BrowserRealWorldValidator:
    """Executes controlled test matrix against public real-world pages."""

    TEST_MATRIX = [
        {"category": "Static HTML", "url": "https://httpbin.org/html", "required": ["html"]},
        {"category": "Dynamic JS / Delay", "url": "https://httpbin.org/delay/1", "required": ["javascript", "network"]},
        {"category": "Forms", "url": "https://httpbin.org/forms/post", "required": ["forms", "html"]},
        {"category": "Cookies", "url": "https://httpbin.org/cookies", "required": ["cookies"]},
        {"category": "Redirects", "url": "https://httpbin.org/redirect/2", "required": ["redirects"]},
        {"category": "SPA / Real Site", "url": "https://news.ycombinator.com", "required": ["links", "dom"]},
    ]

    @classmethod
    async def validate_backend_real_sites(
        cls,
        backend_name: str,
        urls: Optional[List[Dict[str, Any]]] = None,
    ) -> List[WebsiteTestResult]:
        from core.fetch.engine import UniversalFetchEngine

        matrix = urls or cls.TEST_MATRIX
        engine = UniversalFetchEngine()
        results: List[WebsiteTestResult] = []

        for item in matrix:
            cat = item["category"]
            url = item["url"]
            t0 = time.perf_counter()

            try:
                res = await engine.fetch(url, force_tool=backend_name, cache=False)
                dur = (time.perf_counter() - t0) * 1000.0

                # Check if blocked by Cloudflare/anti-bot
                blocked = res.status_code in (403, 503) and ("turnstile" in res.text.lower() or "cloudflare" in res.text.lower() or "challenge" in res.text.lower())

                caps: Dict[str, str] = {
                    "navigation": "PASS" if res.success or res.status_code == 200 else ("BLOCKED" if blocked else "FAIL"),
                    "html": "PASS" if len(res.text) > 50 else "FAIL",
                    "dom": "PASS" if res.title or len(res.links) > 0 else "PARTIAL",
                }

                outcome = res.success and res.status_code < 400
                err_msg = "BLOCKED_BY_SITE" if blocked else res.error

                results.append(
                    WebsiteTestResult(
                        category=cat,
                        url=url,
                        backend=backend_name,
                        success=outcome or blocked,
                        status_code=res.status_code,
                        duration_ms=round(dur, 2),
                        capabilities_verified=caps,
                        blocked_by_site=blocked,
                        error=err_msg,
                    )
                )

            except Exception as e:
                dur = (time.perf_counter() - t0) * 1000.0
                results.append(
                    WebsiteTestResult(
                        category=cat,
                        url=url,
                        backend=backend_name,
                        success=False,
                        status_code=0,
                        duration_ms=round(dur, 2),
                        capabilities_verified={"navigation": "FAIL"},
                        error=str(e),
                    )
                )

        return results
