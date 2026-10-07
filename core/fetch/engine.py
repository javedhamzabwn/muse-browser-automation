"""core/fetch/engine.py — Universal Fetch Engine with Resilient Fallback."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from core.adapters.base import BaseToolAdapter
from core.adapters.browser_adapters import ChromeAdapter, CliBrowserAdapter, ObscuraAdapter, PlaywrightAdapter
from core.adapters.http_adapter import HttpStaticAdapter
from core.adapters.ytdlp_adapter import YtDlpAdapter
from core.fetch.cache import FetchCache
from core.fetch.fallback import CircuitBreaker, ErrorClassifier, FailureMemory, FetchErrorKind
from core.fetch.normalizer import FetchResult
from core.fetch.planner import FetchPlanner
from core.fetch.reddit import RedditFetcher
from core.tools.manifest import ToolStatus
from core.tools.registry import ToolRegistry

logger = logging.getLogger("muse.fetch.engine")


class UniversalFetchEngine:
    """Master orchestrator for content fetching, tier selection, and intelligent fallback."""

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        cache: Optional[FetchCache] = None,
        enable_cache: bool = True,
    ):
        self.registry = registry or ToolRegistry()
        self.cache = cache or FetchCache()
        self.enable_cache = enable_cache
        self.circuit_breaker = CircuitBreaker()
        self.failure_memory = FailureMemory()
        self.reddit = RedditFetcher()

        # Adapter lookup
        self._adapters: Dict[str, BaseToolAdapter] = {
            "http_static": HttpStaticAdapter(),
            "playwright": PlaywrightAdapter(),
            "obscura": ObscuraAdapter(),
            "chrome": ChromeAdapter(),
            "yt-dlp": YtDlpAdapter(),
            "moli": CliBrowserAdapter("moli"),
            "lightpanda": CliBrowserAdapter("lightpanda"),
            "agent-browser": CliBrowserAdapter("agent-browser"),
        }

    async def fetch(
        self,
        url: str,
        requirements: Optional[Dict[str, Any]] = None,
        options: Optional[Dict[str, Any]] = None,
        force_tool: Optional[str] = None,
        cache: bool = True,
    ) -> FetchResult:
        """
        Universal entry point: plans tiers, checks cache, executes fallback chain,
        normalizes output, and persists to cache.
        """
        t0 = time.perf_counter()
        reqs = requirements or {}
        opts = options or {}
        if force_tool:
            opts["force_tool"] = force_tool
        if not cache:
            opts["skip_cache"] = True
        use_cache = self.enable_cache and not opts.get("skip_cache") and not reqs.get("authentication")

        # 1. Check Cache
        if use_cache:
            cached = self.cache.get(url)
            if cached:
                dt_ms = (time.perf_counter() - t0) * 1000.0
                return FetchResult(
                    success=True,
                    tool="cache",
                    url=url,
                    title=cached["title"],
                    content=cached["content"],
                    text=cached["text"],
                    links=cached["links"],
                    metadata=cached["metadata"],
                    timing={"total_ms": round(dt_ms, 2), "cache_ms": round(dt_ms, 2)},
                    status_code=cached["status_code"],
                )

        # 2. Plan Tier Execution Order
        candidate_names = FetchPlanner.plan(url, reqs)
        fallbacks: List[Dict[str, Any]] = []

        # 3. Execute through candidate chain
        for tool_name in candidate_names:
            # Handle specialized Reddit provider
            if tool_name == "redlib":
                red_res = await self.reddit.fetch(url, timeout=opts.get("timeout", 6.0))
                if red_res.success:
                    if use_cache:
                        self.cache.set(url, red_res.title, red_res.content, red_res.text, red_res.links, red_res.metadata)
                    return red_res
                fallbacks.append({"tool": "redlib", "error": red_res.error, "fallbacks": red_res.fallbacks})
                continue

            # Check Circuit Breaker
            if not self.circuit_breaker.is_available(tool_name):
                logger.debug("Skipping %s: circuit breaker open", tool_name)
                continue

            # Check Failure Memory
            known_err = self.failure_memory.is_failing(url, tool_name)
            if known_err:
                logger.debug("Skipping %s on %s: recent %s failure remembered", tool_name, url, known_err.value)
                continue

            # Check Tool Registry for status
            manifest = self.registry.get_tool(tool_name)
            if manifest and not manifest.enabled:
                continue

            adapter = self._adapters.get(tool_name)
            if not adapter:
                continue

            t_step = time.perf_counter()
            try:
                result = await adapter.fetch(url, options=opts)
                dt_step = (time.perf_counter() - t_step) * 1000.0

                if result.success:
                    self.circuit_breaker.record_success(tool_name)
                    result.fallbacks = fallbacks
                    result.timing["total_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)

                    # Cache successful result
                    if use_cache:
                        self.cache.set(
                            url=url,
                            title=result.title,
                            content=result.content,
                            text=result.text,
                            links=result.links,
                            metadata=result.metadata,
                            status_code=result.status_code or 200,
                            is_authenticated=bool(reqs.get("authentication")),
                        )
                    return result

                # Execution returned success=False
                err_kind = ErrorClassifier.classify(result.error, result.status_code)
                self.failure_memory.record_failure(url, tool_name, err_kind)
                self.circuit_breaker.record_failure(tool_name)
                fallbacks.append({
                    "tool": tool_name,
                    "error": result.error,
                    "error_kind": err_kind.value,
                    "duration_ms": round(dt_step, 2),
                })

            except Exception as exc:
                dt_step = (time.perf_counter() - t_step) * 1000.0
                err_kind = ErrorClassifier.classify(exc)
                self.failure_memory.record_failure(url, tool_name, err_kind)
                self.circuit_breaker.record_failure(tool_name)
                fallbacks.append({
                    "tool": tool_name,
                    "error": str(exc),
                    "error_kind": err_kind.value,
                    "duration_ms": round(dt_step, 2),
                })

        # All candidates exhausted
        dt_total = (time.perf_counter() - t0) * 1000.0
        return FetchResult(
            success=False,
            tool="none",
            url=url,
            error="All planned fetch tiers failed",
            fallbacks=fallbacks,
            timing={"total_ms": round(dt_total, 2)},
        )
