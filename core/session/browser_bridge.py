"""core/session/browser_bridge.py — Profile Bridge Connecting Local Browser Sessions to Muse."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from core.session.importer import BrowserSessionImporter
from core.session.validator import SessionValidator
from core.session.vault import SessionVault

logger = logging.getLogger("muse.session.bridge")


class BrowserProfileBridge:
    """Safely connects local user browser profiles to compatible automated backends."""

    def __init__(self, vault: Optional[SessionVault] = None):
        self.vault = vault or SessionVault()
        self.importer = BrowserSessionImporter()

    def discover_sources(self) -> List[Dict[str, Any]]:
        """List available local browser profiles for bridge importation."""
        return self.importer.list_detected_browsers()

    def check_compatibility(self, source_browser: str, target_tool: str) -> Dict[str, Any]:
        """Verify if session state from source can be safely consumed by target tool."""
        matrix = {
            "chrome": {
                "chrome": "FULL (Direct CDP User Profile)",
                "playwright": "HIGH (Cookies + Storage State)",
                "obscura": "HIGH (CDP Cookie Injection)",
                "camoufox": "PARTIAL (Cookies Only)",
                "csi": "FULL (Active Chrome Profile)",
            },
            "edge": {
                "playwright": "HIGH (Cookies + Storage State)",
                "obscura": "HIGH (CDP Cookie Injection)",
                "chrome": "HIGH (Chromium Cookies)",
            },
            "firefox": {
                "camoufox": "FULL (Gecko Profile State)",
                "playwright": "HIGH (Cookies)",
            },
        }

        compat = matrix.get(source_browser.lower(), {}).get(target_tool.lower(), "PARTIAL (Cookies Only)")
        is_supported = not compat.startswith("UNSUPPORTED")

        return {
            "source_browser": source_browser,
            "target_tool": target_tool,
            "supported": is_supported,
            "compatibility_level": compat,
        }

    async def bridge_session(
        self,
        source_browser: str,
        source_profile: str,
        target_domains: List[str],
        target_tools: List[str],
        session_name: Optional[str] = None,
        validate_after_import: bool = False,
    ) -> Dict[str, Any]:
        """
        Imports domain-scoped session and optionally runs immediate zero-secret validation.
        """
        res = self.importer.import_domain_session(
            browser_id=source_browser,
            profile_name=source_profile,
            target_domains=target_domains,
            allowed_tools=target_tools,
            session_name=session_name,
        )

        if not res.get("success"):
            return res

        session_id = res["session"]["session_id"]
        validation_results = {}

        if validate_after_import:
            target_tool = target_tools[0] if target_tools else "playwright"
            val = await SessionValidator.validate_session_online(
                session_id=session_id,
                target_domain=target_domains[0],
                vault=self.vault,
                browser_backend=target_tool,
            )
            validation_results = val

        return {
            "success": True,
            "session": res["session"],
            "validation": validation_results,
        }
