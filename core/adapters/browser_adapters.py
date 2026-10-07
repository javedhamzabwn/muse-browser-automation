"""core/adapters/browser_adapters.py — Browser Backend Adapters for Muse 4.0."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, Optional

from core.adapters.base import BaseToolAdapter
from core.fetch.extractor import SimpleContentExtractor
from core.fetch.normalizer import FetchResult
from core.router import BrowserRouter
from core.types import BrowserBackendType

logger = logging.getLogger("muse.adapters.browser")


class PlaywrightAdapter(BaseToolAdapter):
    """Playwright Chromium headless fast-path adapter."""

    name = "playwright"

    def __init__(self, router: Optional[BrowserRouter] = None):
        self.router = router or BrowserRouter()

    async def fetch(self, url: str, options: Optional[Dict[str, Any]] = None) -> FetchResult:
        opts = options or {}
        t0 = time.perf_counter()
        try:
            backend = await self.router.resolve_backend(BrowserBackendType.PLAYWRIGHT)
            if not await backend.is_connected():
                await backend.start()

            tabs = await backend.list_tabs()
            tid = tabs[0]["tabId"] if tabs else await backend.create_tab(url)
            if tabs:
                await backend.navigate(tid, url)

            title = await backend.get_title(tid)

            # Extract page model or evaluated HTML
            model = await backend.build_page_model(tid)
            text = model.to_markdown()

            t_total = (time.perf_counter() - t0) * 1000.0
            return FetchResult(
                success=True,
                tool=self.name,
                url=url,
                title=title,
                content=text,
                text=text,
                timing={"total_ms": round(t_total, 2)},
                status_code=200,
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


class ObscuraAdapter(BaseToolAdapter):
    """Obscura anti-detect stealth CDP adapter."""

    name = "obscura"

    def __init__(self, router: Optional[BrowserRouter] = None):
        self.router = router or BrowserRouter()

    async def fetch(self, url: str, options: Optional[Dict[str, Any]] = None) -> FetchResult:
        t0 = time.perf_counter()
        try:
            backend = await self.router.resolve_backend(BrowserBackendType.OBSCURA)
            if not await backend.is_connected():
                await backend.start()

            tabs = await backend.list_tabs()
            tid = tabs[0]["tabId"] if tabs else await backend.create_tab(url)
            if tabs:
                await backend.navigate(tid, url)

            title = await backend.get_title(tid)
            model = await backend.build_page_model(tid)
            text = model.to_markdown()

            t_total = (time.perf_counter() - t0) * 1000.0
            return FetchResult(
                success=True,
                tool=self.name,
                url=url,
                title=title,
                content=text,
                text=text,
                timing={"total_ms": round(t_total, 2)},
                status_code=200,
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


class ChromeAdapter(BaseToolAdapter):
    """Personal Chrome MV3 extension real-session adapter."""

    name = "chrome"

    def __init__(self, router: Optional[BrowserRouter] = None):
        self.router = router or BrowserRouter()

    async def fetch(self, url: str, options: Optional[Dict[str, Any]] = None) -> FetchResult:
        t0 = time.perf_counter()
        try:
            backend = await self.router.resolve_backend(BrowserBackendType.CHROME)
            if not await backend.is_connected():
                return FetchResult(
                    success=False,
                    tool=self.name,
                    url=url,
                    error="Chrome extension not connected to daemon",
                    timing={"total_ms": round((time.perf_counter() - t0) * 1000.0, 2)},
                )

            tabs = await backend.list_tabs()
            tid = tabs[0]["tabId"] if tabs else await backend.create_tab(url)
            if tabs:
                await backend.navigate(tid, url)

            title = await backend.get_title(tid)
            model = await backend.build_page_model(tid)
            text = model.to_markdown()

            t_total = (time.perf_counter() - t0) * 1000.0
            return FetchResult(
                success=True,
                tool=self.name,
                url=url,
                title=title,
                content=text,
                text=text,
                timing={"total_ms": round(t_total, 2)},
                status_code=200,
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


class CliBrowserAdapter(BaseToolAdapter):
    """Generic CLI execution adapter for Moli, Lightpanda, and Agent-Browser."""

    def __init__(self, name: str, binary: Optional[str] = None):
        self.name = name
        self.binary = binary

    async def fetch(self, url: str, options: Optional[Dict[str, Any]] = None) -> FetchResult:
        t0 = time.perf_counter()
        binary = self.binary or shutil.which(self.name)
        if not binary or not os.path.isfile(binary):
            return FetchResult(
                success=False,
                tool=self.name,
                url=url,
                error=f"{self.name} executable not installed",
                timing={"total_ms": round((time.perf_counter() - t0) * 1000.0, 2)},
            )

        cmd = [binary]
        if self.name == "moli":
            cmd.extend(["dump", url])
        elif self.name == "lightpanda":
            cmd.extend(["dump", url])
        elif self.name == "agent-browser":
            cmd.extend(["fetch", url])
        else:
            cmd.append(url)

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15.0)
            if res.returncode == 0:
                raw_out = res.stdout
                extracted = SimpleContentExtractor.extract(raw_out, base_url=url)
                t_total = (time.perf_counter() - t0) * 1000.0
                return FetchResult(
                    success=True,
                    tool=self.name,
                    url=url,
                    title=extracted["title"],
                    content=extracted["text"],
                    text=extracted["text"],
                    links=extracted["links"],
                    timing={"total_ms": round(t_total, 2)},
                    status_code=200,
                )
            return FetchResult(
                success=False,
                tool=self.name,
                url=url,
                error=res.stderr.strip()[:150] or f"Exit code {res.returncode}",
                timing={"total_ms": round((time.perf_counter() - t0) * 1000.0, 2)},
            )
        except Exception as exc:
            return FetchResult(
                success=False,
                tool=self.name,
                url=url,
                error=str(exc),
                timing={"total_ms": round((time.perf_counter() - t0) * 1000.0, 2)},
            )
