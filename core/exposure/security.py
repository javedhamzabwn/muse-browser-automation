"""core/exposure/security.py — Capability-Level Public vs Local Access Policy."""

from __future__ import annotations

import enum
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("muse.exposure.security")


class CapabilityGroup(str, enum.Enum):
    BROWSER = "browser"
    FETCHER = "fetcher"
    SYSTEM_INSPECT = "system_inspect"
    MEDIA = "media"
    COMPUTER = "computer_control"
    COMPUTER_CONTROL = "computer_control"
    SESSIONS = "session_vault"
    SESSION_VAULT = "session_vault"
    TERMINAL = "terminal"
    FILESYSTEM = "filesystem"
    CREDENTIALS = "credentials"


class PublicSecurityPolicy:
    """
    Enforces the principle: LOCAL ACCESS != PUBLIC ACCESS.
    Ensures that sensitive host capabilities (computer control, session vault,
    credentials, filesystem, terminal) are not exposed over public tunnels
    without explicit administrator consent.
    """

    DEFAULT_CATEGORY_POLICY = {
        "browser": "ALLOW",
        "fetcher": "ALLOW",
        "system_inspect": "ALLOW",
        "media": "ALLOW",
        "computer_control": "DENY",
        "session_vault": "DENY",
        "terminal": "DENY",
        "filesystem": "DENY",
        "credentials": "DENY",
    }

    TOOL_TO_CATEGORY = {
        # Browser tools
        "browser_task": "browser",
        "browser_open": "browser",
        "browser_extract": "browser",
        "browser_find": "browser",
        "browser_click": "browser",
        "browser_type": "browser",
        "browser_scroll": "browser",
        "browser_screenshot": "browser",
        "browser_tabs": "browser",
        "browser_status": "system_inspect",
        "browser_health": "system_inspect",
        "browser_task_status": "browser",
        "browser_task_cancel": "browser",
        "browser_model": "browser",
        "browser_execute": "browser",
        "browser_detect_captcha": "browser",
        "tabs_list": "browser",
        "tab_switch": "browser",
        "tab_create": "browser",
        "tab_close": "browser",
        "navigate": "browser",
        "click": "browser",
        "type": "browser",
        "screenshot": "browser",
        # Fetcher tools
        "fetch_url": "fetcher",
        "fetch_extract": "fetcher",
        # System & Inspection tools
        "ping": "system_inspect",
        "tool_status": "system_inspect",
        "tool_health": "system_inspect",
        "tools_test": "system_inspect",
        "tools_benchmark": "system_inspect",
        "tools_audit": "system_inspect",
        "tools_configure": "system_inspect",
        "tools_validate": "system_inspect",
        "tools_install": "system_inspect",
        # Computer Control tools
        "computer_click": "computer_control",
        "computer_type": "computer_control",
        "computer_screenshot": "computer_control",
        "computer_windows": "computer_control",
        # Session Vault tools
        "session_list": "session_vault",
        "session_import": "session_vault",
        "session_validate": "session_vault",
        "session_revoke": "session_vault",
    }

    def __init__(self, policy_file: Optional[str] = None):
        self.policy_file = policy_file or os.path.join("state", "public_permissions.json")
        self.policy: Dict[str, str] = dict(self.DEFAULT_CATEGORY_POLICY)
        self._load_policy()

    def _load_policy(self) -> None:
        if os.path.isfile(self.policy_file):
            try:
                with open(self.policy_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.policy.update(data)
            except Exception as e:
                logger.warning("Could not read policy file %s: %s", self.policy_file, e)

        # Allow environment variable overrides
        if os.environ.get("MUSE_ALLOW_PUBLIC_COMPUTER", "").lower() in ("1", "true", "yes"):
            self.policy["computer_control"] = "ALLOW"
        if os.environ.get("MUSE_ALLOW_PUBLIC_SESSION", "").lower() in ("1", "true", "yes"):
            self.policy["session_vault"] = "ALLOW"

    def save_policy(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.policy_file)), exist_ok=True)
        try:
            with open(self.policy_file, "w", encoding="utf-8") as f:
                json.dump(self.policy, f, indent=2)
        except Exception as e:
            logger.warning("Could not save policy file: %s", e)

    @staticmethod
    def is_public_request(headers: Dict[str, Any], remote_ip: Optional[str] = None) -> bool:
        """
        Determines whether an incoming HTTP request originated from an external tunnel
        (such as ngrok) rather than local loopback.
        """
        # 1. Forwarded headers set by reverse proxies / ngrok
        xf_host = headers.get("x-forwarded-host", "") or headers.get("X-Forwarded-Host", "")
        if "ngrok" in xf_host.lower():
            return True

        xf_for = headers.get("x-forwarded-for", "") or headers.get("X-Forwarded-For", "")
        if xf_for and not (xf_for.startswith("127.0.0.1") or xf_for.startswith("::1")):
            return True

        # 2. Host header check
        host = headers.get("host", "") or headers.get("Host", "")
        if "ngrok" in host.lower() or ".dev" in host.lower() or ".app" in host.lower():
            return True

        # 3. Remote IP check
        if remote_ip and remote_ip not in ("127.0.0.1", "::1", "localhost"):
            return True

        return False

    def is_tool_allowed(self, tool_name: str, is_public: bool) -> Tuple[bool, Optional[str]]:
        """
        Validates if tool_name is permitted to be invoked by the caller.
        Local callers are granted access. Public callers are filtered by category policy.
        """
        if not is_public:
            return True, None

        tool_key = f"tool:{tool_name}"
        if tool_key in self.policy:
            verdict = self.policy[tool_key]
            if verdict == "ALLOW":
                return True, None
            return False, f"Access denied: Tool '{tool_name}' is explicitly restricted on public endpoints."

        cat = self.categorize_tool(tool_name)
        verdict = self.policy.get(cat, "DENY")

        if verdict == "ALLOW":
            return True, None

        msg = (
            f"Access denied: Tool '{tool_name}' (category: '{cat}') is restricted on public endpoints. "
            f"Local access != Public access. Set policy or run tool via local gateway (127.0.0.1)."
        )
        return False, msg

    def is_tool_allowed_for_public(self, tool_name: str) -> bool:
        ok, _ = self.is_tool_allowed(tool_name, is_public=True)
        return ok

    def filter_tools_for_caller(self, tools: List[Dict[str, Any]], is_public: bool) -> List[Dict[str, Any]]:
        if not is_public:
            return tools
        return [t for t in tools if self.is_tool_allowed_for_public(t.get("name", ""))]

    @classmethod
    def categorize_tool(cls, tool_name: str) -> str:
        if tool_name in cls.TOOL_TO_CATEGORY:
            return cls.TOOL_TO_CATEGORY[tool_name]
        for prefix in ("browser_", "navigate", "click", "type", "screenshot", "tab"):
            if tool_name.startswith(prefix):
                return CapabilityGroup.BROWSER.value
        for prefix in ("fetch", "http"):
            if tool_name.startswith(prefix):
                return CapabilityGroup.FETCHER.value
        for prefix in ("computer_", "desktop_", "mouse_", "keyboard_"):
            if tool_name.startswith(prefix):
                return CapabilityGroup.COMPUTER.value
        for prefix in ("terminal_", "shell_", "cmd_", "bash_"):
            if tool_name.startswith(prefix):
                return CapabilityGroup.TERMINAL.value
        for prefix in ("session_", "cookie_", "auth_"):
            if tool_name.startswith(prefix):
                return CapabilityGroup.SESSIONS.value
        return CapabilityGroup.SYSTEM_INSPECT.value

    @classmethod
    def is_request_public(cls, headers: Dict[str, Any], remote_ip: Optional[str] = None) -> bool:
        return cls.is_public_request(headers, remote_ip)

    def set_permission(self, category: str, allow: bool) -> None:
        self.policy[category] = "ALLOW" if allow else "DENY"
        self.save_policy()

    def set_tool_permission(self, tool_name: str, allow: bool) -> None:
        self.policy[f"tool:{tool_name}"] = "ALLOW" if allow else "DENY"
        self.save_policy()

    def toggle_tool_permission(self, tool_name: str) -> bool:
        current = self.is_tool_allowed_for_public(tool_name)
        new_val = not current
        self.set_tool_permission(tool_name, new_val)
        return new_val

    def get_policy(self) -> Dict[str, str]:
        return dict(self.policy)
