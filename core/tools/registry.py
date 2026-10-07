"""core/tools/registry.py — Central Tool Registry Singleton for Muse 4.0."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.tools.capabilities import CapabilityMatcher
from core.tools.detector import ToolDetector
from core.tools.health import ToolHealthChecker
from core.tools.installer import ToolInstaller
from core.tools.lifecycle import ToolLifecycleManager
from core.tools.manifest import InstallMethod, ToolCategory, ToolManifest, ToolStatus

logger = logging.getLogger("muse.tools.registry")


class ToolRegistry:
    """Single source of truth for all tools, browsers, fetchers, and utilities."""

    _instance: Optional[ToolRegistry] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_dir: Optional[str] = None):
        if getattr(self, "_initialized", False):
            return

        self.config_dir = config_dir or os.path.join(os.path.expanduser("~"), ".muse")
        self.config_path = os.path.join(self.config_dir, "tools_config.json")
        self._tools: Dict[str, ToolManifest] = {}
        self.lifecycle = ToolLifecycleManager()

        self._register_default_catalog()
        self._load_config()
        self._initialized = True

    def _register_default_catalog(self) -> None:
        """Register initial catalog of all supported browser, fetch, computer, and utility tools."""
        root_dir = str(Path(__file__).resolve().parent.parent.parent)
        registry_file = os.path.join(root_dir, "tools", "registry", "tools.json")

        if os.path.isfile(registry_file):
            try:
                with open(registry_file, "r", encoding="utf-8") as f:
                    reg_data = json.load(f)
                method_map = {
                    "builtin": InstallMethod.BUILTIN,
                    "pip": InstallMethod.PIP,
                    "npm": InstallMethod.NPM,
                    "cargo": InstallMethod.CARGO,
                    "download": InstallMethod.DOWNLOAD,
                    "git": InstallMethod.GIT,
                    "manual": InstallMethod.MANUAL,
                    "system": InstallMethod.SYSTEM,
                }
                for item in reg_data.get("tools", []):
                    cat_val = item.get("category", "utility")
                    if cat_val == "fetching":
                        cat = ToolCategory.FETCHER
                    else:
                        cat = ToolCategory(cat_val) if cat_val in [c.value for c in ToolCategory] else ToolCategory.UTILITY

                    inst_info = item.get("install", {}).get("windows", {})
                    method = method_map.get(inst_info.get("method", "system"), InstallMethod.SYSTEM)
                    binary = inst_info.get("binary")
                    caps = {c: True for c in item.get("capabilities", [])}

                    health_cmd = None
                    hc = item.get("health_check", {})
                    if "command" in hc:
                        health_cmd = hc["command"].split()

                    manifest = ToolManifest(
                        name=item["id"],
                        display_name=item.get("name", item["id"]),
                        category=cat,
                        platforms=["win32", "darwin", "linux"],
                        install_method=method,
                        binary=binary,
                        priority=item.get("default_priority", 50),
                        capabilities=caps,
                        repo_url=item.get("repository"),
                        health_command=health_cmd,
                    )
                    self._tools[manifest.name] = manifest
                if self._tools:
                    return
            except Exception as e:
                logger.warning("Failed to load tools.json: %s. Using hardcoded fallback.", e)

        catalog = [
            # 1. Browsers
            ToolManifest(
                name="playwright",
                display_name="Playwright Chromium",
                category=ToolCategory.BROWSER,
                platforms=["win32", "darwin", "linux"],
                install_method=InstallMethod.PIP,
                priority=10,
                capabilities={
                    "javascript": True,
                    "dom": True,
                    "cookies": True,
                    "headless": True,
                    "headed": True,
                    "screenshots": True,
                    "pdf": True,
                    "downloads": True,
                    "playwright": True,
                    "fast_fetch": True,
                },
                repo_url="https://github.com/microsoft/playwright-python",
            ),
            ToolManifest(
                name="chrome",
                display_name="Google Chrome (Real Profile)",
                category=ToolCategory.BROWSER,
                platforms=["win32", "darwin", "linux"],
                install_method=InstallMethod.SYSTEM,
                priority=20,
                capabilities={
                    "real_browser": True,
                    "javascript": True,
                    "dom": True,
                    "cookies": True,
                    "persistent_session": True,
                    "screenshots": True,
                    "websocket": True,
                    "authentication": True,
                },
                repo_url="https://www.google.com/chrome/",
            ),
            ToolManifest(
                name="obscura",
                display_name="Obscura Stealth Engine",
                category=ToolCategory.BROWSER,
                platforms=["win32", "darwin", "linux"],
                install_method=InstallMethod.GITHUB_RELEASE,
                priority=15,
                capabilities={
                    "javascript": True,
                    "dom": True,
                    "cookies": True,
                    "persistent_session": True,
                    "headless": True,
                    "headed": True,
                    "screenshots": True,
                    "cdp": True,
                    "fast_fetch": True,
                },
                repo_url="https://github.com/h4ckf0r0day/obscura",
            ),
            ToolManifest(
                name="moli",
                display_name="Moli Automation Engine",
                category=ToolCategory.BROWSER,
                platforms=["win32", "darwin", "linux"],
                install_method=InstallMethod.GITHUB_RELEASE,
                binary="moli",
                version_command=["moli", "--version"],
                health_command=["moli", "--version"],
                priority=25,
                capabilities={
                    "javascript": True,
                    "dom": True,
                    "cookies": True,
                    "headless": True,
                    "headed": True,
                    "screenshots": True,
                    "cdp": True,
                    "webdriver": True,
                    "fast_fetch": True,
                },
                repo_url="https://github.com/lexmount/moli",
            ),
            ToolManifest(
                name="lightpanda",
                display_name="Lightpanda Headless AI Browser",
                category=ToolCategory.BROWSER,
                platforms=["win32", "darwin", "linux"],
                install_method=InstallMethod.GITHUB_RELEASE,
                binary="lightpanda",
                version_command=["lightpanda", "--version"],
                health_command=["lightpanda", "--version"],
                priority=12,
                capabilities={
                    "javascript": True,
                    "dom": True,
                    "headless": True,
                    "fast_fetch": True,
                },
                repo_url="https://github.com/lightpanda-io/browser",
            ),
            ToolManifest(
                name="agent-browser",
                display_name="Agent Browser (Vercel Labs)",
                category=ToolCategory.BROWSER,
                platforms=["win32", "darwin", "linux"],
                install_method=InstallMethod.NPM,
                binary="agent-browser",
                version_command=["agent-browser", "--version"],
                health_command=["agent-browser", "--version"],
                priority=30,
                capabilities={
                    "javascript": True,
                    "dom": True,
                    "cookies": True,
                    "headless": True,
                    "screenshots": True,
                    "fast_fetch": True,
                },
                repo_url="https://github.com/vercel-labs/agent-browser",
            ),
            ToolManifest(
                name="camoufox",
                display_name="Camoufox Stealth Firefox",
                category=ToolCategory.BROWSER,
                platforms=["win32", "darwin", "linux"],
                install_method=InstallMethod.PIP,
                priority=35,
                capabilities={
                    "javascript": True,
                    "dom": True,
                    "cookies": True,
                    "headless": True,
                    "headed": True,
                    "playwright": True,
                },
                repo_url="https://github.com/daijro/camoufox",
            ),
            ToolManifest(
                name="csi",
                display_name="CSI Real Chrome Daemon",
                category=ToolCategory.BROWSER,
                platforms=["win32", "darwin", "linux"],
                install_method=InstallMethod.SYSTEM,
                priority=40,
                capabilities={
                    "real_browser": True,
                    "javascript": True,
                    "dom": True,
                    "cookies": True,
                    "persistent_session": True,
                    "authentication": True,
                },
                repo_url="https://github.com/ximing/csi",
            ),
            # 2. Fetchers
            ToolManifest(
                name="http_static",
                display_name="Tier 0 Fast HTTP Fetcher",
                category=ToolCategory.FETCHER,
                platforms=["win32", "darwin", "linux"],
                install_method=InstallMethod.BUILTIN,
                priority=5,
                capabilities={
                    "fast_fetch": True,
                },
            ),
            ToolManifest(
                name="redlib",
                display_name="Redlib Privacy Reddit Fetcher",
                category=ToolCategory.FETCHER,
                platforms=["win32", "darwin", "linux"],
                install_method=InstallMethod.BUILTIN,
                priority=8,
                capabilities={
                    "reddit_fetch": True,
                    "fast_fetch": True,
                },
                repo_url="https://github.com/redlib-org/redlib",
            ),
            # 3. Utilities
            ToolManifest(
                name="yt-dlp",
                display_name="yt-dlp Media Extractor & Downloader",
                category=ToolCategory.UTILITY,
                platforms=["win32", "darwin", "linux"],
                install_method=InstallMethod.PIP,
                binary="yt-dlp",
                version_command=["yt-dlp", "--version"],
                health_command=["yt-dlp", "--version"],
                priority=50,
                capabilities={
                    "video_download": True,
                    "file_download": True,
                },
                repo_url="https://github.com/yt-dlp/yt-dlp",
            ),
            ToolManifest(
                name="ffmpeg",
                display_name="FFmpeg Media Stream Processor",
                category=ToolCategory.UTILITY,
                platforms=["win32", "darwin", "linux"],
                install_method=InstallMethod.SYSTEM,
                binary="ffmpeg",
                version_command=["ffmpeg", "-version"],
                priority=60,
                capabilities={
                    "file_download": True,
                },
                repo_url="https://ffmpeg.org/",
            ),
        ]
        for t in catalog:
            self._tools[t.name] = t

    def get_tool(self, name: str) -> Optional[ToolManifest]:
        return self._tools.get(name)

    def list_tools(self, category: Optional[ToolCategory] = None) -> List[ToolManifest]:
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        return sorted(tools, key=lambda t: t.priority)

    def detect_all(self) -> None:
        """Scan system and detect installation and version for all registered tools."""
        for t in self._tools.values():
            installed, binary, version = ToolDetector.detect_tool(t)
            t.installed = installed
            if binary:
                t.binary = binary
            if version:
                t.version = version
            if not installed:
                t.status = ToolStatus.NOT_INSTALLED
            elif t.status == ToolStatus.UNKNOWN:
                t.status = ToolStatus.READY

    async def check_all_health(self) -> Dict[str, Tuple[ToolStatus, Optional[str]]]:
        """Perform real live health checks across all detected tools."""
        self.detect_all()
        results = {}
        for t in self._tools.values():
            status, detail = await ToolHealthChecker.check_tool_health(t)
            t.status = status
            t.status_detail = detail
            results[t.name] = (status, detail)
        return results

    def find_capable(self, requirements: Dict[str, Any], require_ready: bool = True, preferred_tool: Optional[str] = None) -> List[ToolManifest]:
        """Match and rank tools according to requested capability specification."""
        return CapabilityMatcher.match(
            tools=list(self._tools.values()),
            requirements=requirements,
            require_ready=require_ready,
            preferred_tool=preferred_tool,
        )

    def set_enabled(self, name: str, enabled: bool) -> bool:
        tool = self.get_tool(name)
        if not tool:
            return False
        tool.enabled = enabled
        self._save_config()
        return True

    def set_binary_path(self, name: str, binary_path: str) -> bool:
        tool = self.get_tool(name)
        if not tool:
            return False
        tool.binary = binary_path
        tool.installed = os.path.isfile(binary_path)
        self._save_config()
        return True

    def _save_config(self) -> None:
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            cfg = {
                t.name: {
                    "enabled": t.enabled,
                    "binary": t.binary,
                    "priority": t.priority,
                }
                for t in self._tools.values()
            }
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            logger.error("Failed to save tools config: %s", e)

    def _load_config(self) -> None:
        if not os.path.isfile(self.config_path):
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            for name, overrides in cfg.items():
                if name in self._tools:
                    t = self._tools[name]
                    if "enabled" in overrides:
                        t.enabled = overrides["enabled"]
                    if "binary" in overrides and overrides["binary"]:
                        t.binary = overrides["binary"]
                    if "priority" in overrides:
                        t.priority = overrides["priority"]
        except Exception as e:
            logger.error("Failed to load tools config: %s", e)
