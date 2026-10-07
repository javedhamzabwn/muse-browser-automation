"""core/fetch/normalizer.py — Unified Result Normalization Model for Muse 4.0."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FetchResult:
    """Normalized output schema returned by all fetch and browser backends."""

    success: bool
    tool: str
    url: str
    title: str = ""
    content: str = ""
    text: str = ""
    html: Optional[str] = None
    links: List[Dict[str, str]] = field(default_factory=list)
    images: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timing: Dict[str, float] = field(default_factory=dict)
    fallbacks: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None
    status_code: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.html is None:
            d.pop("html", None)
        return d
