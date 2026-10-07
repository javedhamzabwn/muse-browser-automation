"""core/session/permissions.py — Domain and Tool Scoping Policy Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlparse


@dataclass
class SessionPermissionPolicy:
    """Enforces strict domain scoping and allowed target browser boundaries."""

    allowed_domains: List[str] = field(default_factory=list)
    allowed_tools: List[str] = field(default_factory=list)
    allow_all_tools: bool = False

    def is_domain_allowed(self, target_url_or_domain: str) -> bool:
        """Check if target URL matches one of the scoped domains."""
        if not self.allowed_domains:
            return False

        # Extract domain from URL or raw hostname
        hostname = target_url_or_domain
        if "://" in target_url_or_domain:
            parsed = urlparse(target_url_or_domain)
            hostname = parsed.hostname or ""

        hostname = hostname.lower().strip()
        for d in self.allowed_domains:
            d_clean = d.lower().strip()
            if hostname == d_clean or hostname.endswith(f".{d_clean}"):
                return True
        return False

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check if target browser backend is authorized to consume this session."""
        if self.allow_all_tools:
            return True
        tool_clean = tool_name.lower().strip()
        return tool_clean in [t.lower().strip() for t in self.allowed_tools]
