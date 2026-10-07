"""tests/unit/test_pool.py — Unit tests for Phase 8 Browser Pool & Multi-Tab Workspaces."""

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from core.pool import BrowserPool
from core.types import BrowserBackendType
from tests.synthetic_server import SyntheticServer


class TestBrowserPool(unittest.IsolatedAsyncioTestCase):
    server: SyntheticServer
    pool: BrowserPool
    base_url: str

    async def asyncSetUp(self):
        self.server = SyntheticServer(port=18083)
        self.server.start()
        self.base_url = self.server.url
        self.pool = BrowserPool(max_workspaces=2)

    async def asyncTearDown(self):
        await self.pool.close_all()
        self.server.stop()

    async def test_workspace_isolation_and_operations(self):
        # 1. Allocate Workspace A
        ws_a = await self.pool.get_workspace("ws-alpha", backend_type=BrowserBackendType.PLAYWRIGHT)
        tab_a = await ws_a.open_tab(f"{self.base_url}/synthetic.html")
        self.assertEqual(ws_a.active_tab_id, tab_a)
        self.assertEqual(len(ws_a.tabs), 1)

        # Build page model on A
        model_a = await ws_a.build_page_model()
        self.assertIn("Synthetic Test Suite", model_a.title)

        # 2. Allocate Workspace B (isolated)
        ws_b = await self.pool.get_workspace("ws-beta", backend_type=BrowserBackendType.PLAYWRIGHT)
        tab_b = await ws_b.open_tab(f"{self.base_url}/frame.html")
        self.assertEqual(ws_b.active_tab_id, tab_b)
        self.assertNotEqual(tab_a, tab_b)

        # Check pool listing
        listing = self.pool.list_workspaces()
        self.assertEqual(len(listing), 2)
        wids = {w["workspace_id"] for w in listing}
        self.assertEqual(wids, {"ws-alpha", "ws-beta"})

        # 3. Limit enforcement: 3rd workspace exceeds max_workspaces (2)
        with self.assertRaises(RuntimeError) as ctx:
            await self.pool.get_workspace("ws-gamma", backend_type=BrowserBackendType.PLAYWRIGHT)
        self.assertIn("pool limit reached", str(ctx.exception))

        # 4. Release Workspace A -> now can allocate Gamma
        await self.pool.release_workspace("ws-alpha")
        self.assertEqual(len(self.pool.list_workspaces()), 1)

        ws_g = await self.pool.get_workspace("ws-gamma", backend_type=BrowserBackendType.PLAYWRIGHT)
        self.assertEqual(ws_g.workspace_id, "ws-gamma")


if __name__ == "__main__":
    unittest.main()
