"""core/tools/manifest.py — Tool Metadata & Manifest Specification for Muse 4.0."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ToolCategory(str, Enum):
    BROWSER = "browser"
    FETCHER = "fetcher"
    COMPUTER_CONTROL = "computer_control"
    MEDIA = "media"
    REDDIT = "reddit"
    UTILITY = "utility"


class ToolStatus(str, Enum):
    MISSING = "MISSING"
    NOT_INSTALLED = "NOT_INSTALLED"
    INSTALLED = "INSTALLED"
    STARTING = "STARTING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    RUNNING = "RUNNING"
    ERROR = "ERROR"
    DISABLED = "DISABLED"
    UNKNOWN = "UNKNOWN"


class InstallMethod(str, Enum):
    BUILTIN = "builtin"
    PIP = "pip"
    GITHUB_RELEASE = "github_release"
    NPM = "npm"
    CARGO = "cargo"
    SYSTEM = "system"
    LOCAL = "local"
    DOWNLOAD = "download"
    GIT = "git"
    MANUAL = "manual"


@dataclass
class ToolManifest:
    """Single source of truth definition for each tool in Muse 4.0."""

    name: str
    display_name: str
    category: ToolCategory
    platforms: List[str] = field(default_factory=lambda: ["win32", "darwin", "linux"])
    install_method: InstallMethod = InstallMethod.SYSTEM
    binary: Optional[str] = None
    version_command: Optional[List[str]] = None
    health_command: Optional[List[str]] = None
    start_command: Optional[List[str]] = None
    stop_command: Optional[List[str]] = None
    update_command: Optional[List[str]] = None
    capabilities: Dict[str, bool] = field(default_factory=dict)
    requirements: Dict[str, Any] = field(default_factory=dict)
    priority: int = 50
    enabled: bool = True
    installed: bool = False
    version: Optional[str] = None
    status: ToolStatus = ToolStatus.UNKNOWN
    status_detail: Optional[str] = None
    install_notes: Optional[str] = None
    repo_url: Optional[str] = None

    def has_capability(self, cap: str) -> bool:
        """Check if tool supports given capability."""
        return bool(self.capabilities.get(cap, False))

    def is_platform_supported(self, platform_name: str) -> bool:
        """Check if current operating system platform is supported."""
        if not self.platforms:
            return True
        for p in self.platforms:
            if platform_name.startswith(p):
                return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        if not isinstance(self.version, (str, type(None))):
            self.version = str(self.version)
        data = asdict(self)
        data["category"] = self.category.value
        data["install_method"] = self.install_method.value
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ToolManifest:
        d = dict(data)
        if "category" in d and isinstance(d["category"], str):
            d["category"] = ToolCategory(d["category"])
        if "install_method" in d and isinstance(d["install_method"], str):
            d["install_method"] = InstallMethod(d["install_method"])
        if "status" in d and isinstance(d["status"], str):
            d["status"] = ToolStatus(d["status"])
        return cls(**d)
