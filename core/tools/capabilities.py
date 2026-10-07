"""core/tools/capabilities.py — Capability Declaration & Matching Engine."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from core.tools.manifest import ToolManifest, ToolStatus


class ToolCapability(str, Enum):
    JAVASCRIPT = "javascript"
    DOM = "dom"
    COOKIES = "cookies"
    PERSISTENT_SESSION = "persistent_session"
    REAL_BROWSER = "real_browser"
    HEADLESS = "headless"
    HEADED = "headed"
    SCREENSHOTS = "screenshots"
    PDF = "pdf"
    DOWNLOADS = "downloads"
    CDP = "cdp"
    PLAYWRIGHT = "playwright"
    PUPPETEER = "puppeteer"
    WEBDRIVER = "webdriver"
    WEBSOCKET = "websocket"
    FAST_FETCH = "fast_fetch"
    AUTHENTICATION = "authentication"
    FILE_UPLOAD = "file_upload"
    FILE_DOWNLOAD = "file_download"
    VIDEO_DOWNLOAD = "video_download"
    REDDIT_FETCH = "reddit_fetch"


class CapabilityMatcher:
    """Matches requirements against registered tool capabilities and ranks them."""

    @staticmethod
    def satisfies_requirements(tool: ToolManifest, requirements: Dict[str, Any]) -> bool:
        """Check if a tool satisfies all requested boolean capabilities."""
        if not tool.enabled or not tool.installed:
            return False

        for req_key, req_val in requirements.items():
            if isinstance(req_val, bool) and req_val:
                if not tool.has_capability(req_key):
                    return False
        return True

    @classmethod
    def match(
        cls,
        tools: List[ToolManifest],
        requirements: Dict[str, Any],
        require_ready: bool = True,
        preferred_tool: Optional[str] = None,
    ) -> List[ToolManifest]:
        """Returns sorted list of eligible tools matching requirements."""
        candidates = []
        for t in tools:
            if require_ready and t.status not in (ToolStatus.READY, ToolStatus.RUNNING):
                continue
            if cls.satisfies_requirements(t, requirements):
                candidates.append(t)

        def sort_key(tool: ToolManifest):
            # 1. Preferred tool gets highest rank (-1000)
            is_pref = -1000 if (preferred_tool and tool.name == preferred_tool) else 0
            # 2. Status priority: RUNNING / READY preferred
            status_score = 0 if tool.status in (ToolStatus.READY, ToolStatus.RUNNING) else 100
            # 3. Base priority (lower = higher priority)
            return (is_pref, status_score, tool.priority, tool.name)

        return sorted(candidates, key=sort_key)
