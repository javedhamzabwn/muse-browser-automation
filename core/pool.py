"""core/pool.py — Browser Pool & Multi-Tab Workspaces for Muse 3.0.

Provides isolated workspaces for multi-tenant and multi-task AI agent execution,
enforcing workspace limits, tab tracking, and automatic resource cleanup.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from core.cache import SelectorCache
from core.interfaces import BaseBrowserBackend
from core.page_model import PageModeler
from core.router import BrowserRouter
from core.task_engine import TaskEngine
from core.types import ActionResult, BrowserBackendType, PageModel
from core.verifier import ActionVerifier

logger = logging.getLogger("muse.core.pool")


class BrowserWorkspace:
    """Isolated browser execution workspace with dedicated tabs, cache, and task engine."""

    def __init__(
        self,
        workspace_id: str,
        backend: BaseBrowserBackend,
        cache: Optional[SelectorCache] = None,
        task_engine: Optional[TaskEngine] = None,
    ):
        self.workspace_id = workspace_id
        self.backend = backend
        self.cache = cache or SelectorCache()
        self.task_engine = task_engine or TaskEngine()
        self.verifier = ActionVerifier()
        self.active_tab_id: Optional[str] = None
        self.tabs: List[str] = []
        self.created_at = time.time()
        self.last_used_at = time.time()

    def touch(self) -> None:
        self.last_used_at = time.time()

    async def open_tab(self, url: str = "about:blank") -> str:
        """Open a new tab inside this workspace."""
        self.touch()
        tid = await self.backend.create_tab(url)
        if tid not in self.tabs:
            self.tabs.append(tid)
        self.active_tab_id = tid
        return tid

    async def switch_tab(self, tab_id: str, focus: bool = False) -> None:
        """Switch active tab for this workspace."""
        self.touch()
        await self.backend.switch_tab(tab_id, focus=focus)
        self.active_tab_id = tab_id

    async def close_tab(self, tab_id: str) -> None:
        """Close specified tab in this workspace."""
        self.touch()
        if tab_id in self.tabs:
            self.tabs.remove(tab_id)
        await self.backend.close_tab(tab_id)
        if self.active_tab_id == tab_id:
            self.active_tab_id = self.tabs[0] if self.tabs else None

    async def navigate(self, url: str, wait_until: str = "load") -> bool:
        """Navigate active tab to URL."""
        self.touch()
        if not self.active_tab_id:
            await self.open_tab(url)
            return True
        return await self.backend.navigate(self.active_tab_id, url, wait_until)

    async def build_page_model(self) -> PageModel:
        """Generate structured PageModel for active tab."""
        self.touch()
        if not self.active_tab_id:
            await self.open_tab()
        return await PageModeler.build(self.backend, self.active_tab_id or "")

    async def execute_action(
        self,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        verify: bool = True,
        expected_change: Optional[str] = None,
        timeout_ms: int = 1000,
    ) -> ActionResult:
        """Execute verified action on workspace's active tab."""
        self.touch()
        if not self.active_tab_id:
            raise RuntimeError("Workspace has no active tab")

        router = BrowserRouter()
        return await router.execute_action(
            tab_id=self.active_tab_id,
            action=action,
            params=params,
            verify=verify,
            expected_change=expected_change,
            timeout_ms=timeout_ms,
            backend=self.backend,
        )

    async def close(self) -> None:
        """Close all tabs and free workspace resources."""
        for tid in list(self.tabs):
            try:
                await self.backend.close_tab(tid)
            except Exception:
                pass
        self.tabs.clear()
        self.active_tab_id = None


class BrowserPool:
    """Pool managing multiple isolated browser workspaces."""

    def __init__(
        self,
        max_workspaces: int = 5,
        idle_timeout_sec: float = 600.0,
    ):
        self.max_workspaces = max_workspaces
        self.idle_timeout_sec = idle_timeout_sec
        self._workspaces: Dict[str, BrowserWorkspace] = {}
        self._router = BrowserRouter()

    async def get_workspace(
        self,
        workspace_id: str,
        backend_type: BrowserBackendType = BrowserBackendType.AUTO,
    ) -> BrowserWorkspace:
        """Retrieve existing workspace or provision a new isolated workspace."""
        if workspace_id in self._workspaces:
            ws = self._workspaces[workspace_id]
            ws.touch()
            return ws

        if len(self._workspaces) >= self.max_workspaces:
            # Clean idle workspaces
            await self._cleanup_idle()
            if len(self._workspaces) >= self.max_workspaces:
                raise RuntimeError(
                    f"Browser pool limit reached ({self.max_workspaces} workspaces). "
                    "Close idle workspaces before allocating new ones."
                )

        backend = await self._router.resolve_backend(backend_type)
        if not await backend.is_connected():
            await backend.start()

        ws = BrowserWorkspace(workspace_id=workspace_id, backend=backend)
        self._workspaces[workspace_id] = ws
        return ws

    async def release_workspace(self, workspace_id: str) -> None:
        """Close and release a workspace."""
        ws = self._workspaces.pop(workspace_id, None)
        if ws:
            await ws.close()

    async def close_all(self) -> None:
        """Terminate all active workspaces."""
        for ws in list(self._workspaces.values()):
            await ws.close()
        self._workspaces.clear()

    async def _cleanup_idle(self) -> None:
        """Evict workspaces that exceeded idle timeout."""
        now = time.time()
        for wid, ws in list(self._workspaces.items()):
            if now - ws.last_used_at > self.idle_timeout_sec:
                logger.info("Evicting idle workspace: %s", wid)
                await ws.close()
                self._workspaces.pop(wid, None)

    def list_workspaces(self) -> List[Dict[str, Any]]:
        """List active workspaces and their resource stats."""
        now = time.time()
        return [
            {
                "workspace_id": wid,
                "backend": ws.backend.backend_type.value,
                "active_tab": ws.active_tab_id,
                "tabs_count": len(ws.tabs),
                "idle_sec": round(now - ws.last_used_at, 1),
            }
            for wid, ws in self._workspaces.items()
        ]
