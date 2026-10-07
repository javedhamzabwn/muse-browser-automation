"""core/tools/selector.py — Intelligent Tool Selector with User Preferences & Fallback."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.tools.manifest import ToolCategory, ToolManifest, ToolStatus

logger = logging.getLogger("muse.tools.selector")


@dataclass
class SelectionResult:
    tool: ToolManifest
    fallback_from: Optional[str] = None
    reason: str = "preferred"
    candidate_chain: List[str] = field(default_factory=list)


class ToolSelector:
    """Selects the best healthy tool according to capabilities and user preferences."""

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = workspace_root or str(Path(__file__).resolve().parent.parent.parent)
        self.config_path = os.path.join(self.workspace_root, "state", "preferences.json")
        self.preferences: Dict[str, Any] = self._load_preferences()

    def _load_preferences(self) -> Dict[str, Any]:
        default_prefs = {
            "browser_backend": "AUTO",       # "AUTO", "obscura", "playwright", "chrome", etc.
            "computer_backend": "AUTO",      # "AUTO", "zavora-computer-use", "pyautogui-mcp", etc.
            "fetcher_backend": "AUTO",       # "AUTO", "http_static", "playwright", etc.
            "reddit_backend": "AUTO",        # "AUTO", "redlib"
            "media_backend": "yt-dlp",       # "yt-dlp"
            "tool_overrides": {
                # tool_name: "preferred" | "fallback" | "disabled"
            },
        }
        if os.path.isfile(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_prefs.update(data)
            except Exception as e:
                logger.warning("Could not read preferences: %s", e)
        return default_prefs

    def save_preferences(self) -> None:
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.preferences, f, indent=2)
        except Exception as e:
            logger.error("Failed to save preferences: %s", e)

    def set_tool_preference(self, tool_id: str, preference: str) -> None:
        """Set preference for a tool: 'preferred', 'fallback', or 'disabled'."""
        if preference not in ("preferred", "fallback", "disabled"):
            raise ValueError(f"Invalid preference: {preference}. Must be preferred, fallback, or disabled.")
        self.preferences.setdefault("tool_overrides", {})[tool_id] = preference
        self.save_preferences()

    def set_category_backend(self, category: str, backend: str) -> None:
        key = f"{category}_backend"
        self.preferences[key] = backend
        self.save_preferences()

    def select(
        self,
        tools: List[ToolManifest],
        requirements: Dict[str, Any],
        category: Optional[ToolCategory] = None,
        failed_tools: Optional[List[str]] = None,
    ) -> Optional[SelectionResult]:
        """Select optimal tool for given requirements respecting health and user preferences."""
        failed_set = set(failed_tools or [])
        overrides = self.preferences.get("tool_overrides", {})

        # Filter by category if specified
        candidates = [t for t in tools if category is None or t.category == category]

        # Filter out disabled tools and known failures in current chain
        active = [
            t for t in candidates
            if t.enabled
            and overrides.get(t.name) != "disabled"
            and t.name not in failed_set
        ]

        if not active:
            return None

        # Check required capabilities
        capable: List[ToolManifest] = []
        for t in active:
            match = True
            for req, val in requirements.items():
                if val and not t.has_capability(req):
                    match = False
                    break
            if match:
                capable.append(t)

        if not capable:
            capable = active

        # Score and rank candidates:
        # Priority rule:
        # 1. User preferred for category or tool override 'preferred' (+1000)
        # 2. Status READY (+100) vs INSTALLED (+50) vs UNKNOWN (0) vs DEGRADED (-50)
        # 3. Tool override 'fallback' (-200)
        # 4. Manifest default priority (lower number = higher precedence)
        cat_pref = None
        if category:
            cat_pref = self.preferences.get(f"{category.value}_backend")

        def score_tool(t: ToolManifest) -> int:
            score = 500 - t.priority
            override = overrides.get(t.name)
            if override == "preferred" or (cat_pref and cat_pref.lower() == t.name.lower()):
                score += 1000
            elif override == "fallback":
                score -= 200

            if t.status == ToolStatus.READY:
                score += 200
            elif t.status == ToolStatus.INSTALLED or t.installed:
                score += 100
            elif t.status == ToolStatus.DEGRADED:
                score -= 100
            elif t.status in (ToolStatus.MISSING, ToolStatus.NOT_INSTALLED):
                score -= 500
            return score

        ranked = sorted(capable, key=score_tool, reverse=True)
        chosen = ranked[0]
        fallback_from = failed_tools[-1] if failed_tools else None
        chain = [t.name for t in ranked]

        return SelectionResult(
            tool=chosen,
            fallback_from=fallback_from,
            reason="preference_match" if overrides.get(chosen.name) == "preferred" else "capability_match",
            candidate_chain=chain,
        )
