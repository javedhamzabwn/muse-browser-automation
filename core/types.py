"""core/types.py — Strongly-typed models for Muse Browser Automation 3.0."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class BrowserBackendType(str, Enum):
    AUTO = "auto"
    CHROME = "chrome"
    OBSCURA = "obscura"
    PLAYWRIGHT = "playwright"
    CAMOUFOX = "camoufox"
    MOLI = "moli"
    AGENT_BROWSER = "agent-browser"


class ResolutionMethod(str, Enum):
    CACHE = "cache"
    DETERMINISTIC = "deterministic"
    SEMANTIC = "semantic"
    STRUCTURAL = "structural"
    VISION = "vision"
    FALLBACK = "fallback"


class ActionRiskLevel(str, Enum):
    LOW = "low"            # Navigate, read, scroll
    MEDIUM = "medium"      # Click link, fill text
    HIGH = "high"          # Delete, submit payment, change password
    CRITICAL = "critical"  # Wire transfer, external webhook execution


@dataclass
class ElementBounds:
    x: int
    y: int
    w: int
    h: int

    @property
    def center_x(self) -> int:
        return self.x + (self.w // 2)

    @property
    def center_y(self) -> int:
        return self.y + (self.h // 2)


@dataclass
class ElementQuery:
    description: Optional[str] = None
    selector: Optional[str] = None
    role: Optional[str] = None
    name: Optional[str] = None
    text: Optional[str] = None
    aria_label: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None
    ref: Optional[str] = None
    timeout_ms: int = 5000
    allow_shadow_dom: bool = True
    allow_iframes: bool = True


@dataclass
class ResolvedElement:
    ref: str
    tag: str
    role: str
    name: str
    bounds: ElementBounds
    selector: str
    method: ResolutionMethod
    confidence: float
    attributes: Dict[str, str] = field(default_factory=dict)
    iframe_index: Optional[int] = None
    in_shadow_dom: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["bounds"] = asdict(self.bounds)
        d["bounds"]["center_x"] = self.bounds.center_x
        d["bounds"]["center_y"] = self.bounds.center_y
        d["method"] = self.method.value
        return d


@dataclass
class VerificationResult:
    verified: bool
    page_changed: bool
    url_changed: bool = False
    title_changed: bool = False
    dom_mutated: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionResult:
    ok: bool
    action: str
    duration_ms: float
    verification: Optional[VerificationResult] = None
    element: Optional[ResolvedElement] = None
    data: Any = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "action": self.action,
            "duration_ms": round(self.duration_ms, 2),
            "verification": asdict(self.verification) if self.verification else None,
            "element": self.element.to_dict() if self.element else None,
            "data": self.data,
            "error": self.error,
        }


@dataclass
class PageModel:
    url: str
    title: str
    interactive_elements: List[ResolvedElement] = field(default_factory=list)
    buttons: List[Dict[str, Any]] = field(default_factory=list)
    links: List[Dict[str, Any]] = field(default_factory=list)
    inputs: List[Dict[str, Any]] = field(default_factory=list)
    forms: List[Dict[str, Any]] = field(default_factory=list)
    iframes: List[Dict[str, Any]] = field(default_factory=list)
    dialogs: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    viewport: Dict[str, int] = field(default_factory=dict)
    scroll_info: Dict[str, int] = field(default_factory=dict)

    def to_compact_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "elements_count": len(self.interactive_elements),
            "buttons_count": len(self.buttons),
            "inputs_count": len(self.inputs),
            "links_count": len(self.links),
            "iframes_count": len(self.iframes),
            "dialogs_count": len(self.dialogs),
            "summary": self.summary,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "interactive_elements": [e.to_dict() for e in self.interactive_elements],
            "buttons": self.buttons,
            "links": self.links,
            "inputs": self.inputs,
            "forms": self.forms,
            "iframes": self.iframes,
            "dialogs": self.dialogs,
            "summary": self.summary,
            "viewport": self.viewport,
            "scroll_info": self.scroll_info,
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Page: {self.title or 'Untitled'} ({self.url})",
        ]
        if self.viewport:
            lines.append(f"Viewport: {self.viewport.get('width', 0)}x{self.viewport.get('height', 0)}")
        if self.scroll_info:
            lines.append(f"Scroll: Y={self.scroll_info.get('y', 0)}/{self.scroll_info.get('height', 0)}")
        
        open_dialogs = [
            f"{d.get('tag', 'dialog')} #{d.get('id', '')} ('{d.get('name', '')}')".strip()
            for d in self.dialogs
            if d.get("open")
        ]
        if open_dialogs:
            lines.append(f"Active Modals: {', '.join(open_dialogs)}")
        else:
            lines.append("Active Modals: None")

        if self.iframes:
            lines.append(f"Iframes: {len(self.iframes)} detected")

        lines.append(f"\n## Interactive Elements ({len(self.interactive_elements)}):")
        for el in self.interactive_elements:
            flags = []
            if el.in_shadow_dom:
                flags.append("shadow-root")
            iframe_path = el.attributes.get("iframe_path")
            if iframe_path:
                flags.append(f"iframe:{iframe_path}")
            elif el.iframe_index is not None:
                flags.append(f"iframe:{el.iframe_index}")
            flag_str = f" [{' '.join(flags)}]" if flags else ""

            b = el.bounds
            id_str = f" (id: {el.attributes.get('id')})" if el.attributes.get("id") else ""
            val = el.attributes.get("value")
            val_str = f" [val: '{val}']" if val else ""
            lines.append(
                f"- [{el.ref}] {el.tag} \"{el.name}\"{id_str}{val_str} [bounds: {b.x},{b.y},{b.w}x{b.h}]{flag_str}"
            )

        return "\n".join(lines)


@dataclass
class TaskCheckpoint:
    task_id: str
    step_index: int
    action: str
    state: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)


@dataclass
class BrowserConfig:
    backend: BrowserBackendType = BrowserBackendType.AUTO
    cdp_host: str = "127.0.0.1"
    cdp_port: int = 9222
    daemon_url: str = "http://127.0.0.1:18010"
    timeout_ms: int = 15000
    risk_threshold: ActionRiskLevel = ActionRiskLevel.HIGH
    auth_token: Optional[str] = None
