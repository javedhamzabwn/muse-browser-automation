"""core/interfaces.py — Universal interfaces for Muse Browser Automation 3.0."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from core.types import (
    ActionResult,
    BrowserBackendType,
    ElementQuery,
    PageModel,
    ResolvedElement,
    TaskCheckpoint,
    VerificationResult,
)


class BaseBrowserBackend(ABC):
    """Abstract base class for all browser backends (Chrome, Obscura, Playwright, Camoufox)."""

    @property
    @abstractmethod
    def backend_type(self) -> BrowserBackendType:
        """Returns the specific backend identifier."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this browser backend is installed and capable of running."""
        ...

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if connection to the browser instance is live."""
        ...

    @abstractmethod
    async def start(self) -> None:
        """Initialize or connect to the browser backend."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully disconnect or terminate the browser backend."""
        ...

    # Tab Operations
    @abstractmethod
    async def list_tabs(self) -> List[Dict[str, Any]]:
        """List active tabs accessible to automation."""
        ...

    @abstractmethod
    async def create_tab(self, url: str = "about:blank") -> str:
        """Create a new tab and return its tabId."""
        ...

    @abstractmethod
    async def switch_tab(self, tab_id: str, focus: bool = False) -> None:
        """Set active automation tab. Never steals window focus unless focus=True."""
        ...

    @abstractmethod
    async def close_tab(self, tab_id: str) -> None:
        """Close specified tab."""
        ...

    # Navigation & Page State
    @abstractmethod
    async def navigate(self, tab_id: str, url: str, wait_until: str = "load") -> bool:
        """Navigate to URL and wait until specified lifecycle event."""
        ...

    @abstractmethod
    async def get_title(self, tab_id: str) -> str:
        """Get document title."""
        ...

    @abstractmethod
    async def get_url(self, tab_id: str) -> str:
        """Get current URL."""
        ...

    @abstractmethod
    async def evaluate(self, tab_id: str, expression: str) -> Any:
        """Execute JavaScript expression inside the page and return result."""
        ...

    # Input Actions
    @abstractmethod
    async def click(self, tab_id: str, x: int, y: int) -> bool:
        """Dispatch trusted click at coordinates."""
        ...

    @abstractmethod
    async def type_text(self, tab_id: str, text: str) -> bool:
        """Insert text into currently focused element."""
        ...

    @abstractmethod
    async def press_key(self, tab_id: str, key: str) -> bool:
        """Dispatch keyboard key press."""
        ...

    @abstractmethod
    async def scroll(self, tab_id: str, delta_x: int = 0, delta_y: int = 400) -> bool:
        """Scroll viewport or targeted element."""
        ...

    # Extraction & Observation
    @abstractmethod
    async def screenshot(self, tab_id: str, full_page: bool = False) -> bytes:
        """Capture screenshot as PNG bytes."""
        ...

    @abstractmethod
    async def build_page_model(self, tab_id: str) -> PageModel:
        """Construct structured PageModel representation of interactive elements."""
        ...

    # Session & State
    @abstractmethod
    async def get_cookies(self, tab_id: str) -> List[Dict[str, Any]]:
        """Retrieve full cookie jar."""
        ...

    @abstractmethod
    async def set_cookies(self, tab_id: str, cookies: List[Dict[str, Any]]) -> bool:
        """Inject cookies into session."""
        ...


class BaseElementResolver(ABC):
    """Abstract resolver for finding elements using the 3-Layer priority path."""

    @abstractmethod
    async def resolve(
        self, backend: BaseBrowserBackend, tab_id: str, query: ElementQuery
    ) -> Optional[ResolvedElement]:
        """Resolve an element query following Cache -> Layer 1 -> Layer 2 -> Layer 3."""
        ...


class BaseActionVerifier(ABC):
    """Abstract verifier for checking whether a dispatched action succeeded."""

    @abstractmethod
    async def verify_action(
        self,
        backend: BaseBrowserBackend,
        tab_id: str,
        action: str,
        before_state: Dict[str, Any],
        expected_change: Optional[str] = None,
        timeout_ms: int = 1500,
    ) -> VerificationResult:
        """Event-driven verification of UI state change without arbitrary sleeps."""
        ...


class BaseSelectorCache(ABC):
    """Abstract storage for learned, self-healing selectors."""

    @abstractmethod
    def get(self, domain: str, page_pattern: str, intent: str) -> Optional[str]:
        """Lookup cached selector for specific intent on a page."""
        ...

    @abstractmethod
    def put(
        self,
        domain: str,
        page_pattern: str,
        intent: str,
        selector: str,
        method: str,
        confidence: float,
    ) -> None:
        """Store working selector."""
        ...

    @abstractmethod
    def record_failure(self, domain: str, page_pattern: str, intent: str) -> None:
        """Mark cached selector as decayed/failed to trigger self-healing."""
        ...


class BaseTaskEngine(ABC):
    """Abstract engine managing multi-step workflows, checkpoints, and retries."""

    @abstractmethod
    async def create_checkpoint(self, checkpoint: TaskCheckpoint) -> None:
        """Persist a task checkpoint."""
        ...

    @abstractmethod
    async def load_last_checkpoint(self, task_id: str) -> Optional[TaskCheckpoint]:
        """Retrieve latest verified checkpoint for task resumption."""
        ...
