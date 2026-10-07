"""core/tools/connection_manager.py — Tracks runtime tool connection states and active roles."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from core.tools.manifest import ToolCategory, ToolManifest, ToolStatus

logger = logging.getLogger("muse.tools.connection")


@dataclass
class ToolConnectionState:
    tool_id: str
    name: str
    category: str
    installed: bool
    running: bool
    connected: bool
    healthy: bool
    role: str               # e.g. "Browser primary", "Browser fallback", "Disabled"
    status: str             # READY, DEGRADED, MISSING, etc.
    status_detail: Optional[str] = None


class ToolConnectionManager:
    """Manages active tool connectivity, running process handles, and assigned roles."""

    def __init__(self, registry: Any, selector: Any):
        self.registry = registry
        self.selector = selector

    def get_all_states(self) -> List[ToolConnectionState]:
        states: List[ToolConnectionState] = []
        tools: List[ToolManifest] = self.registry.list_tools()
        prefs = self.selector.preferences
        overrides = prefs.get("tool_overrides", {})

        for t in tools:
            # Determine role
            cat_backend = prefs.get(f"{t.category.value}_backend", "AUTO")
            override = overrides.get(t.name)

            if override == "disabled":
                role = "Disabled"
            elif override == "preferred" or (cat_backend.lower() == t.name.lower()):
                role = f"{t.category.value.capitalize()} primary"
            elif override == "fallback":
                role = f"{t.category.value.capitalize()} fallback"
            else:
                role = f"{t.category.value.capitalize()} auto"

            # Check if running
            is_running = self.registry.lifecycle.is_running(t.name)
            is_healthy = t.status == ToolStatus.READY
            is_installed = t.installed or t.status in (ToolStatus.READY, ToolStatus.INSTALLED)

            states.append(
                ToolConnectionState(
                    tool_id=t.name,
                    name=t.display_name,
                    category=t.category.value,
                    installed=is_installed,
                    running=is_running,
                    connected=is_running or (is_healthy and is_installed),
                    healthy=is_healthy,
                    role=role,
                    status=t.status.value,
                    status_detail=t.status_detail,
                )
            )
        return states

    def format_summary(self) -> str:
        states = self.get_all_states()
        lines = ["=== Muse Tool Connection Manager ==="]
        for s in states:
            lines.append(f"\n{s.name} ({s.tool_id}):")
            lines.append(f"  Installed : {'YES' if s.installed else 'NO'}")
            lines.append(f"  Running   : {'YES' if s.running else 'NO'}")
            lines.append(f"  Healthy   : {'YES' if s.healthy else 'NO'}")
            lines.append(f"  Role      : {s.role}")
            lines.append(f"  Status    : {s.status}")
        lines.append("\n======================================")
        return "\n".join(lines)
